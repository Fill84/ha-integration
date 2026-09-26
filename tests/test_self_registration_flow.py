"""The desktop creates its own HA entry; a hub is never created by this flow."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "desktop_app"


class FakeConfigFlow:
    def __init_subclass__(cls, **_kwargs):
        return super().__init_subclass__()

    async def async_set_unique_id(self, value):
        self.unique_id = value

    def _abort_if_unique_id_configured(self, **_kwargs):
        return None

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


def load_flow(monkeypatch):
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = FakeConfigFlow
    config_entries.ConfigFlowResult = dict
    monkeypatch.setitem(sys.modules, "homeassistant", types.ModuleType("homeassistant"))
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    package = types.ModuleType("self_registration_component")
    package.__path__ = [str(SOURCE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    for name in ("const", "config_flow"):
        fullname = f"{package.__name__}.{name}"
        spec = importlib.util.spec_from_file_location(fullname, SOURCE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, module)
        spec.loader.exec_module(module)
    return sys.modules[f"{package.__name__}.config_flow"].DesktopAppConfigFlow


def test_first_device_and_interrupted_retry_keep_one_entry(monkeypatch):
    flow_class = load_flow(monkeypatch)
    entries = []
    flow = flow_class()
    flow.hass = types.SimpleNamespace(
        config_entries=types.SimpleNamespace(async_entries=lambda _domain: entries)
    )
    assert asyncio.run(flow.async_step_user())["type"] == "form"

    data = {
        "device_id": "pc-1",
        "device_name": "Phill-PC",
        "webhook_id": "a" * 64,
        "app_version": "1.0.6",
    }
    created = asyncio.run(flow.async_step_user(data))
    assert created == {"type": "create_entry", "title": "Phill-PC", "data": data}
    assert created["data"].get("is_hub") is None

    entries.append(types.SimpleNamespace(data=data))
    retry = asyncio.run(flow.async_step_user({**data, "webhook_id": "b" * 64}))
    assert retry["type"] == "abort"
    assert retry["reason"] == "already_registered"
    assert retry["description_placeholders"]["webhook_id"] == "a" * 64


def test_manual_or_malformed_flow_cannot_create_empty_hub(monkeypatch):
    flow_class = load_flow(monkeypatch)
    flow = flow_class()
    flow.hass = types.SimpleNamespace(
        config_entries=types.SimpleNamespace(async_entries=lambda _domain: [])
    )
    for data in ({}, {"device_id": "pc-1", "device_name": "PC"}):
        result = asyncio.run(flow.async_step_user(data))
        assert result == {"type": "abort", "reason": "register_from_desktop"}
