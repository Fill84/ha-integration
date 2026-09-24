"""Registration must not hand an existing webhook to another HA user."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "custom_components/desktop_app"


def test_existing_device_requires_owner_or_admin(monkeypatch):
    def module(name, **values):
        item = types.ModuleType(name)
        item.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, item)
        return item

    class Response:
        def __init__(self, data, status=200):
            self.data, self.status = data, status

    module("aiohttp")
    module("aiohttp.web", Request=object, Response=Response,
           json_response=lambda data, status=200: Response(data, status))
    module("homeassistant")
    module("homeassistant.components", webhook=types.SimpleNamespace())
    module("homeassistant.components.http", KEY_HASS_USER="hass_user")
    module("homeassistant.core", HomeAssistant=object)
    module("homeassistant.helpers")
    module("homeassistant.helpers.device_registry", DeviceInfo=dict)
    module("homeassistant.helpers.http", HomeAssistantView=object)
    package = module("permission_component")
    package.__path__ = [str(SOURCE)]

    def load(name):
        fullname = f"permission_component.{name}"
        spec = importlib.util.spec_from_file_location(fullname, SOURCE / f"{name}.py")
        value = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, value)
        spec.loader.exec_module(value)
        return value

    const = load("const")
    load("helpers")
    api = load("http_api")
    entry = types.SimpleNamespace(entry_id="entry-1", data={
        "device_id": "device-1", "device_name": "Office PC",
        "webhook_id": "secret-hook", "owner_user_id": "alice",
    })
    updates = []
    hass = types.SimpleNamespace(
        data={const.DOMAIN: {const.DATA_LOADED_DEVICES: {"entry-1"}}},
        config_entries=types.SimpleNamespace(
            async_entries=lambda _domain: [entry],
            async_update_entry=lambda *args, **kwargs: updates.append((args, kwargs)),
        ),
    )
    repaired = []
    api._ensure_webhook_registered = lambda *args: repaired.append(args)

    class Request:
        app = {"hass": hass}

        def __init__(self, user_id, is_admin=False):
            self.user = types.SimpleNamespace(id=user_id, is_admin=is_admin)

        def __getitem__(self, key):
            assert key == "hass_user"
            return self.user

        async def json(self):
            return {"device_id": "device-1", "device_name": "Office PC"}

    view = api.DesktopAppRegistrationView()
    denied = asyncio.run(view.post(Request("bob")))
    assert denied.status == 403
    assert not repaired and not updates

    allowed = asyncio.run(view.post(Request("alice")))
    assert allowed.status == 200
    assert allowed.data["webhook_id"] == "secret-hook"
    assert len(repaired) == 1
