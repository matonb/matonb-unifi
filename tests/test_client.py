import json

import httpx
import pytest
import respx

from matonb_unifi import (
    UnifiAPIError,
    UnifiAuthError,
    UnifiClient,
    UnifiConnectionError,
    UnifiError,
)
from matonb_unifi.models import PortOverride, UnifiDevice

DEVICE_URL = "https://unifi.test/proxy/network/api/s/default/stat/device"
REST_URL = "https://unifi.test/proxy/network/api/s/default/rest/device/sw1"

SWITCH = {
    "_id": "sw1",
    "mac": "de:ad:be:ef:00:02",
    "name": "office-switch",
    "type": "usw",
    "port_overrides": [{"port_idx": 2, "poe_mode": "off"}],
    "port_table": [{"port_idx": 1, "poe_mode": "auto"}],
}


@pytest.fixture
def client():
    return UnifiClient("https://unifi.test", api_key="test-key")


@respx.mock
def test_get_clients_returns_stas(client):
    respx.get("https://unifi.test/proxy/network/api/s/default/stat/sta").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "mac": "aa:bb:cc:dd:ee:ff",
                        "last_ip": "10.0.0.1",
                        "name": "my-pc",
                        "hostname": "",
                    },
                    {
                        "mac": "11:22:33:44:55:66",
                        "fixed_ip": "10.0.0.2",
                        "name": "",
                        "hostname": "printer",
                    },
                ]
            },
        )
    )
    stas = client.get_clients()

    assert len(stas) == 2
    assert stas[0].mac == "aa:bb:cc:dd:ee:ff"
    assert stas[0].ip == "10.0.0.1"
    assert stas[0].name == "my-pc"
    assert stas[1].ip == "10.0.0.2"
    assert stas[1].hostname == "printer"


@respx.mock
def test_get_clients_no_ip_is_none(client):
    respx.get("https://unifi.test/proxy/network/api/s/default/stat/sta").mock(
        return_value=httpx.Response(200, json={"data": [{"mac": "aa:bb:cc:dd:ee:ff"}]})
    )
    stas = client.get_clients()

    assert stas[0].ip is None


@respx.mock
def test_get_devices_maps_fields(client):
    respx.get("https://unifi.test/proxy/network/api/s/default/stat/device").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "_id": "abc123",
                        "mac": "de:ad:be:ef:00:01",
                        "ip": "192.168.1.1",
                        "name": "gateway",
                        "type": "ugw",
                        "model": "UGW3",
                        "port_overrides": [{"port_idx": 2, "poe_mode": "off"}],
                    }
                ]
            },
        )
    )
    devices = client.get_devices()

    assert len(devices) == 1
    d = devices[0]
    assert isinstance(d, UnifiDevice)
    assert d.id == "abc123"
    assert d.mac == "de:ad:be:ef:00:01"
    assert d.ip == "192.168.1.1"
    assert d.device_type == "ugw"
    assert d.model == "UGW3"
    assert len(d.port_overrides) == 1
    assert d.port_overrides[0].port_idx == 2
    assert d.port_overrides[0].poe_mode == "off"


@respx.mock
def test_get_devices_maps_port_table(client):
    respx.get("https://unifi.test/proxy/network/api/s/default/stat/device").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "_id": "sw1",
                        "mac": "de:ad:be:ef:00:02",
                        "name": "switch",
                        "type": "usw",
                        "port_overrides": [{"port_idx": 1, "poe_mode": "off"}],
                        "port_table": [
                            {
                                "port_idx": 1,
                                "name": "Port 1",
                                "poe_mode": "auto",
                                "poe_enable": True,
                            },
                            {
                                "port_idx": 2,
                                "name": "Port 2",
                                "poe_mode": "auto",
                                "poe_enable": True,
                            },
                        ],
                    }
                ]
            },
        )
    )
    device = client.get_devices()[0]

    assert len(device.ports) == 2
    assert device.ports[0].port_idx == 1
    assert device.ports[0].name == "Port 1"
    # Override wins over port_table for port 1...
    assert device.current_poe_mode(1) == "off"
    # ...but port 2 falls back to the live port_table value.
    assert device.current_poe_mode(2) == "auto"
    assert device.current_poe_mode(99) == "unknown"


@respx.mock
def test_set_port_poe_accepts_portoverride_objects(client):
    route = respx.put(
        "https://unifi.test/proxy/network/api/s/default/rest/device/abc123"
    ).mock(return_value=httpx.Response(200, json={"data": []}))
    client.set_port_poe(
        "abc123",
        port_modes={3: "off"},
        current_overrides=[PortOverride(port_idx=1, poe_mode="off")],
    )

    payload = json.loads(route.calls.last.request.content)
    overrides_by_port = {
        o["port_idx"]: o["poe_mode"] for o in payload["port_overrides"]
    }
    assert overrides_by_port == {1: "off", 3: "off"}


@respx.mock
def test_set_port_poe_merges_overrides(client):
    route = respx.put(
        "https://unifi.test/proxy/network/api/s/default/rest/device/abc123"
    ).mock(return_value=httpx.Response(200, json={"data": []}))
    client.set_port_poe(
        "abc123",
        port_modes={3: "off", 5: "auto"},
        current_overrides=[
            {"port_idx": 3, "poe_mode": "auto"},
            {"port_idx": 1, "poe_mode": "off"},
        ],
    )

    payload = json.loads(route.calls.last.request.content)
    overrides_by_port = {
        o["port_idx"]: o["poe_mode"] for o in payload["port_overrides"]
    }
    assert overrides_by_port[3] == "off"
    assert overrides_by_port[5] == "auto"
    assert overrides_by_port[1] == "off"


def test_requires_auth():
    with pytest.raises(ValueError, match="api_key or both"):
        UnifiClient("https://unifi.test")


@respx.mock
def test_legacy_api_path():
    respx.get("https://unifi.test/api/s/default/stat/sta").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    c = UnifiClient("https://unifi.test", api_key="k", legacy=True)
    stas = c.get_clients()
    assert stas == []


@respx.mock
def test_find_device_by_name_and_mac(client):
    respx.get(DEVICE_URL).mock(
        return_value=httpx.Response(200, json={"data": [SWITCH]})
    )
    assert client.find_device("office-switch").id == "sw1"
    # MAC lookup is case-insensitive and accepts dashes.
    assert client.find_device("DE-AD-BE-EF-00-02").id == "sw1"
    assert client.find_device("nope") is None


@respx.mock
def test_set_port_poe_takes_overrides_from_device(client):
    respx.get(DEVICE_URL).mock(
        return_value=httpx.Response(200, json={"data": [SWITCH]})
    )
    route = respx.put(REST_URL).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    device = client.get_devices()[0]
    client.set_port_poe(device, {1: "off"})  # no current_overrides supplied

    payload = json.loads(route.calls.last.request.content)
    by_port = {o["port_idx"]: o["poe_mode"] for o in payload["port_overrides"]}
    # Existing override (port 2) is preserved; port 1 is added.
    assert by_port == {2: "off", 1: "off"}


@respx.mock
def test_set_port_poe_by_id_refetches_overrides(client):
    respx.get(DEVICE_URL).mock(
        return_value=httpx.Response(200, json={"data": [SWITCH]})
    )
    route = respx.put(REST_URL).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    # Only the id is supplied, so overrides must be fetched from the API.
    client.set_port_poe("sw1", {1: "off"})

    payload = json.loads(route.calls.last.request.content)
    by_port = {o["port_idx"]: o["poe_mode"] for o in payload["port_overrides"]}
    assert by_port == {2: "off", 1: "off"}


@respx.mock
def test_cycle_port_poe(client):
    respx.get(DEVICE_URL).mock(
        return_value=httpx.Response(200, json={"data": [SWITCH]})
    )
    route = respx.put(REST_URL).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    device = client.get_devices()[0]
    client.cycle_port_poe(device, [1], delay=0)

    assert route.call_count == 2
    off = json.loads(route.calls[0].request.content)
    on = json.loads(route.calls[1].request.content)
    assert {o["port_idx"]: o["poe_mode"] for o in off["port_overrides"]}[1] == "off"
    assert {o["port_idx"]: o["poe_mode"] for o in on["port_overrides"]}[1] == "auto"


@respx.mock
def test_auth_error_on_401(client):
    respx.get(DEVICE_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(UnifiAuthError):
        client.get_devices()


@respx.mock
def test_api_error_carries_status_code(client):
    respx.get(DEVICE_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(UnifiAPIError) as exc:
        client.get_devices()
    assert exc.value.status_code == 500


@respx.mock
def test_connection_error(client):
    respx.get(DEVICE_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(UnifiConnectionError):
        client.get_devices()


@respx.mock
def test_login_failure_raises_auth_error():
    respx.post("https://unifi.test/api/auth/login").mock(
        return_value=httpx.Response(401)
    )
    c = UnifiClient("https://unifi.test", username="admin", password="bad")  # noqa: S106
    with pytest.raises(UnifiAuthError):
        c.login()


@respx.mock
def test_context_manager_logs_in_applies_token_and_logs_out():
    login = respx.post("https://unifi.test/api/auth/login").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "TOKEN=tok123; Path=/"})
    )
    sta = respx.get("https://unifi.test/proxy/network/api/s/default/stat/sta").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    logout = respx.post("https://unifi.test/api/auth/logout").mock(
        return_value=httpx.Response(200)
    )

    with UnifiClient("https://unifi.test", username="admin", password="pw") as unifi:  # noqa: S106
        assert unifi.get_clients() == []

    assert login.called
    assert logout.called
    # The token from the login cookie is carried on subsequent requests.
    assert sta.calls.last.request.headers["X-Auth-Token"] == "tok123"


@respx.mock
def test_set_port_poe_unknown_id_raises(client):
    respx.get(DEVICE_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(UnifiError, match="Device not found"):
        client.set_port_poe("missing", {1: "off"})
