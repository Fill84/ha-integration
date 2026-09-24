"""Missing binary measurements must not be reported as false."""

import importlib.util
import sys
import types
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "desktop_app"


def test_missing_binary_value_is_unknown(monkeypatch):
    def module(name, **values):
        value = types.ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    module("homeassistant")
    module("homeassistant.components")
    module("homeassistant.components.binary_sensor", BinarySensorEntity=type("BinarySensorEntity", (), {}))
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.core", HomeAssistant=object, callback=lambda value: value)
    module("homeassistant.helpers")
    module("homeassistant.helpers.dispatcher", async_dispatcher_connect=lambda *args: None)
    module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    module("homeassistant.helpers.entity_registry", async_get=lambda *args: None)
    package = module("binary_unknown_component")
    package.__path__ = [str(SOURCE)]
    module("binary_unknown_component.entity", DesktopAppEntity=type("DesktopAppEntity", (), {}))

    fullname = "binary_unknown_component.binary_sensor"
    spec = importlib.util.spec_from_file_location(fullname, SOURCE / "binary_sensor.py")
    sensor_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, fullname, sensor_module)
    spec.loader.exec_module(sensor_module)

    sensor = sensor_module.DesktopAppBinarySensor()
    sensor._update_state(True)
    assert sensor._attr_is_on is True
    sensor._update_state(None)
    assert sensor._attr_is_on is None
    sensor._update_state(False)
    assert sensor._attr_is_on is False
