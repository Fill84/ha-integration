"""Entity metadata updates must reach already registered HA entities."""

import importlib.util
import sys
import types
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "desktop_app"


def test_reregistration_changes_name_category_and_clears_icon(monkeypatch):
    def module(name, **values):
        value = types.ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    class RestoreEntity:
        def async_write_ha_state(self):
            self.writes += 1

    module("homeassistant")
    module("homeassistant.core", HomeAssistant=object, callback=lambda value: value)
    module("homeassistant.helpers")
    module("homeassistant.helpers.dispatcher", async_dispatcher_connect=lambda *args: None)
    module("homeassistant.helpers.restore_state", RestoreEntity=RestoreEntity)
    package = module("metadata_component")
    package.__path__ = [str(SOURCE)]

    def load(name):
        fullname = f"metadata_component.{name}"
        spec = importlib.util.spec_from_file_location(fullname, SOURCE / f"{name}.py")
        value = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, value)
        spec.loader.exec_module(value)
        return value

    const = load("const")
    entity_module = load("entity")
    entity = entity_module.DesktopAppEntity(
        None,
        {const.ATTR_DEVICE_ID: "device"},
        {
            const.ATTR_SENSOR_UNIQUE_ID: "cpu_usage",
            const.ATTR_SENSOR_NAME: "CPU Usage",
            const.ATTR_SENSOR_ICON: "mdi:cpu-64-bit",
            const.ATTR_SENSOR_ENTITY_CATEGORY: "diagnostic",
        },
    )
    entity.writes = 0
    entity._handle_update({
        const.ATTR_SENSOR_NAME: "Processor Usage",
        const.ATTR_SENSOR_ICON: None,
        const.ATTR_SENSOR_ENTITY_CATEGORY: None,
    })

    assert entity._attr_unique_id == "device_cpu_usage"
    assert entity._attr_name == "Processor Usage"
    assert entity._attr_icon == "mdi:desktop-tower-monitor"
    assert entity._attr_entity_category is None
    assert entity.writes == 1
