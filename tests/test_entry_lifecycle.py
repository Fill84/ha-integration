"""A failed device setup must not leave a live webhook or timer behind."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "desktop_app"


@pytest.fixture
def entry_env(monkeypatch):
    registered = set()
    stopped = []
    unloaded = []

    def module(name, **values):
        value = types.ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    def register(_hass, _domain, _name, webhook_id, _handler, **_kwargs):
        registered.add(webhook_id)

    def unregister(_hass, webhook_id):
        registered.discard(webhook_id)

    module("homeassistant")
    module("homeassistant.components")
    module("homeassistant.components.webhook", async_register=register, async_unregister=unregister)
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.core", HomeAssistant=object)
    module("homeassistant.helpers")
    module("homeassistant.helpers.device_registry", async_get=lambda _hass: types.SimpleNamespace(
        async_get_or_create=lambda **_kwargs: None,
    ))
    module("homeassistant.helpers.storage", Store=object)

    package = module("entry_component")
    package.__path__ = [str(SOURCE)]

    def load(name):
        fullname = f"entry_component.{name}"
        spec = importlib.util.spec_from_file_location(fullname, SOURCE / f"{name}.py")
        value = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, value)
        spec.loader.exec_module(value)
        return value

    const = load("const")
    module("entry_component.http_api", **{
        name: object for name in (
            "DesktopAppDataView", "DesktopAppPingView", "DesktopAppPingViewWithSlash",
            "DesktopAppRegistrationView",
        )
    })
    module("entry_component.webhook", handle_webhook=lambda *args: None)
    module("entry_component.availability", start_availability_timer=lambda _hass: (
        lambda: stopped.append(True)
    ))
    entry_module = load("__init__")

    async def forward(_entry, _platforms):
        return None

    async def unload(entry, _platforms):
        unloaded.append(entry.entry_id)
        return True

    hass = types.SimpleNamespace(
        data={const.DOMAIN: {
            const.DATA_PENDING_UPDATES: {},
            const.DATA_LOADED_DEVICES: set(),
            const.DATA_LAST_SEEN: {},
            const.DATA_AVAILABILITY_STATE: {},
            const.DATA_UPDATE_INTERVALS: {},
        }},
        config_entries=types.SimpleNamespace(
            async_forward_entry_setups=forward,
            async_unload_platforms=unload,
        ),
    )

    def entry(device_id):
        return types.SimpleNamespace(entry_id=device_id, data={
            const.ATTR_DEVICE_ID: device_id,
            const.ATTR_WEBHOOK_ID: f"hook-{device_id}",
        })

    return entry_module, hass, const, entry, registered, stopped, unloaded


def test_failed_first_entry_cleans_runtime_resources(entry_env):
    component, hass, const, make_entry, registered, stopped, unloaded = entry_env

    async def fail(_entry, _platforms):
        raise RuntimeError("platform unavailable")

    hass.config_entries.async_forward_entry_setups = fail
    with pytest.raises(RuntimeError, match="platform unavailable"):
        asyncio.run(component.async_setup_entry(hass, make_entry("first")))

    runtime = hass.data[const.DOMAIN]
    assert not registered
    assert runtime[const.DATA_PENDING_UPDATES] == {}
    assert const.DATA_AVAILABILITY_TIMER not in runtime
    assert stopped == [True]
    assert unloaded == ["first"]


def test_failed_second_entry_keeps_existing_device_running(entry_env):
    component, hass, const, make_entry, registered, stopped, unloaded = entry_env
    asyncio.run(component.async_setup_entry(hass, make_entry("first")))

    async def fail(_entry, _platforms):
        raise RuntimeError("second platform unavailable")

    hass.config_entries.async_forward_entry_setups = fail
    with pytest.raises(RuntimeError, match="second platform unavailable"):
        asyncio.run(component.async_setup_entry(hass, make_entry("second")))

    runtime = hass.data[const.DOMAIN]
    assert registered == {"hook-first"}
    assert runtime[const.DATA_LOADED_DEVICES] == {"first"}
    assert set(runtime[const.DATA_PENDING_UPDATES]) == {"hook-first"}
    assert const.DATA_AVAILABILITY_TIMER in runtime
    assert stopped == []
    assert unloaded == ["second"]


def test_cancelled_setup_releases_its_resources(entry_env):
    component, hass, const, make_entry, registered, stopped, unloaded = entry_env

    async def cancel(_entry, _platforms):
        raise asyncio.CancelledError

    hass.config_entries.async_forward_entry_setups = cancel
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(component.async_setup_entry(hass, make_entry("cancelled")))

    assert not registered
    assert hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES] == {}
    assert const.DATA_AVAILABILITY_TIMER not in hass.data[const.DOMAIN]
    assert stopped == [True]
    assert unloaded == ["cancelled"]


def test_failed_device_removal_keeps_sensor_metadata_for_retry(entry_env):
    component, hass, const, make_entry, _, _, _ = entry_env
    device = make_entry("first")
    metadata = {const.ATTR_DEVICE_ID: "first", const.ATTR_SENSOR_UNIQUE_ID: "cpu"}
    runtime = hass.data[const.DOMAIN]
    runtime[const.DATA_REGISTERED_SENSORS] = {"first_cpu": metadata}

    async def fail_save(_hass):
        raise OSError("disk full")

    component._async_save_store = fail_save
    with pytest.raises(OSError, match="disk full"):
        asyncio.run(component.async_remove_entry(hass, device))
    assert runtime[const.DATA_REGISTERED_SENSORS] == {"first_cpu": metadata}
