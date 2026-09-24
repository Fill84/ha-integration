"""Exercise real webhook handlers with a small HA boundary stub."""

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "desktop_app"


@pytest.fixture
def webhook_env(monkeypatch):
    signals = []

    def module(name, **values):
        value = types.ModuleType(name)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    class Response:
        def __init__(self, data, status=200):
            self.data = data
            self.status = status

    module("aiohttp")
    module("aiohttp.web", Request=object, Response=Response,
           json_response=lambda data, status=200: Response(data, status))
    module("homeassistant")
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.core", HomeAssistant=object)
    module("homeassistant.helpers")
    module("homeassistant.helpers.device_registry", DeviceInfo=dict)
    module("homeassistant.helpers.dispatcher",
           async_dispatcher_send=lambda *args: signals.append(args))
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    module("homeassistant.util", dt=types.SimpleNamespace(utcnow=lambda: now))
    package = module("contract_component")
    package.__path__ = [str(SOURCE)]
    saves = []
    async def save_store(_hass):
        saves.append(True)
    package._async_save_store = save_store

    def load(name):
        fullname = f"contract_component.{name}"
        spec = importlib.util.spec_from_file_location(fullname, SOURCE / f"{name}.py")
        value = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, fullname, value)
        spec.loader.exec_module(value)
        return value

    const = load("const")
    load("helpers")
    webhook = load("webhook")
    entry = types.SimpleNamespace(data={"device_id": "device", "webhook_id": "hook"})
    hass = types.SimpleNamespace(
        data={const.DOMAIN: {const.DATA_LAST_SEEN: {}, const.DATA_PENDING_UPDATES: {}}},
        config_entries=types.SimpleNamespace(async_entries=lambda domain: [entry]),
    )

    class Request:
        def __init__(self, payload):
            self.payload = payload

        async def json(self):
            return self.payload

    async def send(payload):
        return await webhook.handle_webhook(hass, "hook", Request(payload))

    return send, hass, const, signals, saves


def test_invalid_payload_never_counts_as_heartbeat(webhook_env):
    send, hass, const, signals, _ = webhook_env
    for payload in [None, [], {"type": []}, {"type": ["bad"]},
                    {"type": "update_sensor_states", "data": None},
                    {"type": "register_sensor", "data": {}},
                    {"type": "update_sensor_states", "data": {"sensors": [None]}}]:
        response = asyncio.run(send(payload))
        assert response.status == 400
    assert hass.data[const.DOMAIN][const.DATA_LAST_SEEN] == {}
    assert signals == []


def test_valid_empty_update_acknowledges_heartbeat_and_offline_clears_it(webhook_env):
    send, hass, const, signals, _ = webhook_env
    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [], "update_interval": 600,
    }}))
    assert response.status == 200 and response.data["success"] is True
    assert response.data["protocol_version"] == 1
    state = hass.data[const.DOMAIN]
    assert state[const.DATA_LAST_SEEN]["device"]
    assert state[const.DATA_UPDATE_INTERVALS]["device"] == 600
    assert state[const.DATA_AVAILABILITY_STATE]["device"] is True

    response = asyncio.run(send({"type": "device_offline", "data": {}}))
    assert response.status == 200
    assert "device" not in state[const.DATA_LAST_SEEN]
    assert state[const.DATA_AVAILABILITY_STATE]["device"] is False
    assert signals[-1][-1] is False


def test_unchanged_registration_skips_store_write(webhook_env):
    send, hass, const, signals, saves = webhook_env
    payload = {"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
        "sensor_state": 12,
    }}
    assert asyncio.run(send(payload)).status == 200
    assert len(saves) == 1
    payload["data"]["sensor_state"] = 21
    payload["data"]["sensor_attributes"] = {"source": "new-reading"}
    assert asyncio.run(send(payload)).status == 200
    assert len(saves) == 1
    update = hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"]["device_cpu_usage"]
    assert update == {
        const.ATTR_SENSOR_STATE: 21,
        const.ATTR_SENSOR_ATTRIBUTES: {"source": "new-reading"},
    }
    assert signals[-2][1] == const.SIGNAL_SENSOR_UPDATE.format("device", "cpu_usage")
    assert signals[-2][2] == update


def test_changed_registration_updates_all_metadata_without_changing_unique_id(webhook_env):
    send, hass, const, signals, saves = webhook_env
    payload = {"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage",
        "sensor_type": "sensor", "sensor_state": 12,
        "sensor_icon": "mdi:cpu-64-bit", "sensor_entity_category": "diagnostic",
    }}
    assert asyncio.run(send(payload)).status == 200
    payload["data"].update({
        "sensor_name": "Processor Usage", "sensor_state": 31,
        "sensor_icon": None, "sensor_entity_category": None,
    })
    assert asyncio.run(send(payload)).status == 200
    assert len(saves) == 2
    assert list(hass.data[const.DOMAIN][const.DATA_REGISTERED_SENSORS]) == ["device_cpu_usage"]
    update = hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"]["device_cpu_usage"]
    assert update[const.ATTR_SENSOR_NAME] == "Processor Usage"
    assert update[const.ATTR_SENSOR_ICON] is None
    assert update[const.ATTR_SENSOR_ENTITY_CATEGORY] is None
    assert update[const.ATTR_SENSOR_STATE] == 31
    assert signals[-2][1] == const.SIGNAL_SENSOR_UPDATE.format("device", "cpu_usage")


def test_reregistration_cannot_move_an_existing_entity_to_another_domain(webhook_env):
    send, hass, const, signals, saves = webhook_env
    data = {"sensor_unique_id": "online", "sensor_name": "Online", "sensor_type": "sensor"}
    assert asyncio.run(send({"type": "register_sensor", "data": data})).status == 200
    before_signals = len(signals)
    data["sensor_type"] = "binary_sensor"
    response = asyncio.run(send({"type": "register_sensor", "data": data}))
    assert response.status == 409
    assert len(saves) == 1
    assert len(signals) == before_signals
    stored = hass.data[const.DOMAIN][const.DATA_REGISTERED_SENSORS]["device_online"]
    assert stored[const.ATTR_SENSOR_TYPE] == "sensor"


def test_partial_state_update_preserves_unmentioned_icon_and_attributes(webhook_env):
    send, hass, const, signals, _ = webhook_env
    assert asyncio.run(send({"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
    }})).status == 200
    assert asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_state": 42}],
    }})).status == 200
    update = hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"]["device_cpu_usage"]
    assert update == {const.ATTR_SENSOR_STATE: 42}
    assert signals[-2][2] == update


def test_snapshot_clears_missing_values_without_changing_registered_ids(webhook_env):
    send, hass, const, signals, saves = webhook_env
    for sensor_id, dynamic in (("cpu_usage", True), ("last_boot", False)):
        response = asyncio.run(send({"type": "register_sensor", "data": {
            "sensor_unique_id": sensor_id, "sensor_name": sensor_id,
            "sensor_type": "sensor", "sensor_state": 12,
            "update_at_interval": dynamic,
        }}))
        assert response.status == 200

    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [], "snapshot_scope": "dynamic",
    }}))
    assert response.status == 200
    pending = hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"]
    assert pending["device_cpu_usage"][const.ATTR_SENSOR_STATE] is None
    assert "device_last_boot" not in pending
    assert "device_cpu_usage" in hass.data[const.DOMAIN][const.DATA_REGISTERED_SENSORS]

    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [], "snapshot_scope": "all",
    }}))
    assert response.status == 200
    assert pending["device_last_boot"][const.ATTR_SENSOR_STATE] is None
    assert len(saves) == 2


def test_legacy_update_does_not_clear_missing_values(webhook_env):
    send, hass, const, signals, _ = webhook_env
    asyncio.run(send({"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
    }}))
    response = asyncio.run(send({"type": "update_sensor_states", "data": {"sensors": []}}))
    assert response.status == 200
    assert hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"] == {}
    assert not any(signal[1] == const.SIGNAL_SENSOR_UPDATE.format("device", "cpu_usage")
                   for signal in signals)


def test_invalid_snapshot_scope_is_rejected_before_heartbeat(webhook_env):
    send, hass, const, _, _ = webhook_env
    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [], "snapshot_scope": "everything",
    }}))
    assert response.status == 400
    assert hass.data[const.DOMAIN][const.DATA_LAST_SEEN] == {}


@pytest.mark.parametrize("payload", [
    {"type": "register_sensor", "data": {
        "sensor_unique_id": ["cpu_usage"], "sensor_name": "CPU Usage", "sensor_type": "sensor",
    }},
    {"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu\nusage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
    }},
    {"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
        "sensor_attributes": [],
    }},
    {"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_attributes": []}],
        "update_interval": 60,
    }},
    {"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_icon": 42}],
        "update_interval": 60,
    }},
    {"type": "update_registration", "data": {"device_name": {"bad": "name"}}},
    {"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
        "sensor_state": {"unexpected": "object"},
    }},
    {"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_state": float("nan")}],
        "update_interval": 60,
    }},
    {"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_state": [1, 2]}],
        "update_interval": 60,
    }},
    {"type": "register_sensor\n", "data": {}},
    {"protocol_version": 2, "type": "update_sensor_states", "data": {"sensors": []}},
    {"protocol_version": True, "type": "update_sensor_states", "data": {"sensors": []}},
])
def test_malformed_sensor_commands_do_not_mutate_state(webhook_env, payload):
    send, hass, const, signals, saves = webhook_env
    response = asyncio.run(send(payload))
    assert response.status == 400
    state = hass.data[const.DOMAIN]
    assert state[const.DATA_LAST_SEEN] == {}
    assert state.get(const.DATA_UPDATE_INTERVALS, {}) == {}
    assert state.get(const.DATA_REGISTERED_SENSORS, {}) == {}
    assert signals == []
    assert saves == []


def test_unknown_and_duplicate_sensors_are_rejected_before_heartbeat(webhook_env):
    send, hass, const, signals, _ = webhook_env
    for sensors in (
        [{"sensor_unique_id": "missing", "sensor_state": 1}],
        [{"sensor_unique_id": "missing", "sensor_state": 1}] * 2,
    ):
        response = asyncio.run(send({"type": "update_sensor_states", "data": {
            "sensors": sensors, "update_interval": 60,
        }}))
        assert response.status in (400, 409)
    state = hass.data[const.DOMAIN]
    assert state[const.DATA_LAST_SEEN] == {}
    assert state.get(const.DATA_UPDATE_INTERVALS, {}) == {}
    assert state[const.DATA_PENDING_UPDATES] == {}
    assert signals == []


def test_registered_sensor_update_is_accepted(webhook_env):
    send, hass, const, signals, _ = webhook_env
    assert asyncio.run(send({"type": "register_sensor", "data": {
        "sensor_unique_id": "cpu_usage", "sensor_name": "CPU Usage", "sensor_type": "sensor",
    }})).status == 200
    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": [{"sensor_unique_id": "cpu_usage", "sensor_state": 42}],
        "update_interval": 60,
    }}))
    assert response.status == 200
    assert hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES]["hook"]["device_cpu_usage"][const.ATTR_SENSOR_STATE] == 42
    assert hass.data[const.DOMAIN][const.DATA_UPDATE_INTERVALS]["device"] == 60
    assert any(signal[1] == const.SIGNAL_SENSOR_UPDATE.format("device", "cpu_usage") for signal in signals)


def test_oversized_sensor_batch_is_rejected_without_heartbeat(webhook_env):
    send, hass, const, signals, _ = webhook_env
    sensors = [
        {"sensor_unique_id": f"sensor_{index}", "sensor_state": index}
        for index in range(513)
    ]
    response = asyncio.run(send({"type": "update_sensor_states", "data": {
        "sensors": sensors, "update_interval": 60,
    }}))
    assert response.status == 400
    assert hass.data[const.DOMAIN][const.DATA_LAST_SEEN] == {}
    assert hass.data[const.DOMAIN][const.DATA_PENDING_UPDATES] == {}
    assert signals == []
