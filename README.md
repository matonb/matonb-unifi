# matonb-unifi

[![CI](https://github.com/matonb/matonb-unifi/actions/workflows/ci.yml/badge.svg)](https://github.com/matonb/matonb-unifi/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/matonb-unifi.svg)](https://pypi.org/project/matonb-unifi/)
[![Python versions](https://img.shields.io/pypi/pyversions/matonb-unifi.svg)](https://pypi.org/project/matonb-unifi/)
[![License: MIT](https://img.shields.io/pypi/l/matonb-unifi.svg)](https://github.com/matonb/matonb-unifi/blob/main/LICENSE)

A small, typed Python client for the [UniFi Network API](https://ubntwiki.com/products/software/unifi-controller/api).

Built on [`httpx`](https://www.python-httpx.org/), it returns plain dataclasses
instead of raw JSON and supports both modern UniFi OS (UDM / API key) and legacy
standalone controllers (username / password).

## Features

- API-key auth for modern UniFi OS, or username/password for legacy controllers
- Typed return values (`UnifiSta`, `UnifiDevice`, `Port`, `PortOverride`) — no dict spelunking
- Context-manager lifecycle that logs in and out for you
- Read client stations and infrastructure devices
- Look up a device by name or MAC with `find_device()`
- Set per-port PoE mode, including a built-in `cycle_port_poe()` power-cycle helper
- Typed exception hierarchy (`UnifiError` and friends) — no need to catch `httpx`

## Requirements

- Python >= 3.10
- `httpx >= 0.27`

## Installation

```bash
pip install matonb-unifi
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add matonb-unifi
```

> Internal homelab builds are published to the Gitea package registry at
> `gitea.bm-home.lan/bm-home/matonb-unifi`.

## Quick start

### Modern UniFi OS (API key)

Generate an API key in the UniFi console under
**Settings → Control Plane → Integrations**.

```python
from matonb_unifi import UnifiClient

with UnifiClient("https://192.168.1.1", api_key="your-api-key") as unifi:
    for sta in unifi.get_clients():
        print(sta.name or sta.hostname or sta.mac, "->", sta.ip)

    for dev in unifi.get_devices():
        print(dev.name, dev.model, dev.ip)
```

### Legacy controller (username / password)

```python
from matonb_unifi import UnifiClient

with UnifiClient(
    "https://unifi.example.com:8443",
    username="admin",
    password="secret",
    legacy=True,
    verify_ssl=False,  # controller uses a self-signed certificate
) as unifi:
    devices = unifi.get_devices()
```

When credentials are supplied, the context manager calls `login()` on enter and
`logout()` on exit automatically. With an API key, no login round-trip is needed.

> TLS certificates are verified by default. Many UniFi controllers ship a
> self-signed certificate — pass `verify_ssl=False` to connect to those, as an
> informed opt-out rather than a silent default.

## Configuration

`UnifiClient(base_url, **options)`

| Argument      | Type    | Default     | Description                                                        |
|---------------|---------|-------------|--------------------------------------------------------------------|
| `base_url`    | `str`   | *required*  | Controller URL, e.g. `https://192.168.1.1`                         |
| `api_key`     | `str`   | `None`      | API key for modern UniFi OS (`X-API-KEY`)                          |
| `username`    | `str`   | `None`      | Username for legacy auth (requires `password`)                     |
| `password`    | `str`   | `None`      | Password for legacy auth (requires `username`)                     |
| `site`        | `str`   | `"default"` | UniFi site name                                                    |
| `verify_ssl`  | `bool`  | `True`      | Verify TLS certificates; set `False` for self-signed controllers   |
| `legacy`      | `bool`  | `False`     | Use legacy API paths (`/api/s/...` instead of `/proxy/network/...`) |
| `timeout`     | `float` | `30.0`      | Per-request timeout in seconds                                     |

You must provide either `api_key` **or** both `username` and `password`;
otherwise the constructor raises `ValueError`.

## API

### `get_clients() -> list[UnifiSta]`

Returns all connected client stations (wired and wireless).

```python
@dataclass
class UnifiSta:
    mac: str
    ip: str | None = None   # last_ip, falling back to fixed_ip
    hostname: str = ""
    name: str = ""
```

### `get_devices() -> list[UnifiDevice]`

Returns all UniFi infrastructure devices (switches, APs, gateways, UDMs).

```python
@dataclass
class UnifiDevice:
    id: str                                  # UniFi _id, used for updates
    mac: str
    name: str
    device_type: str                         # e.g. "usw", "uap", "ugw", "udm"
    model: str = "Generic"
    ip: str | None = None
    port_overrides: list[PortOverride] = []  # admin-configured overrides
    ports: list[Port] = []                   # live port_table status

    def current_poe_mode(self, port_idx: int) -> str:
        """Effective PoE mode for a port: an override wins, else the live
        port_table value, else "unknown"."""

@dataclass
class PortOverride:
    port_idx: int
    poe_mode: str = "auto"

@dataclass
class Port:
    port_idx: int
    name: str = ""
    poe_mode: str = ""        # live value reported by the device
    poe_enable: bool = False
```

Use `current_poe_mode()` to read a port's effective state without juggling
overrides and `port_table` yourself:

```python
switch = next(d for d in unifi.get_devices() if d.name == "office-switch")
print(switch.current_poe_mode(3))   # -> "auto", "off", or "unknown"
```

### `find_device(identifier) -> UnifiDevice | None`

Look up a single device by **name or MAC address** (case-insensitive; the MAC
may use `:` or `-` separators). Returns `None` if nothing matches.

```python
switch = unifi.find_device("office-switch")      # by name
switch = unifi.find_device("de-ad-be-ef-00-02")  # by MAC
```

### `set_port_poe(device, port_modes, current_overrides=None) -> None`

Sets the PoE mode for one or more switch ports in a single API call. Existing
overrides are merged, so untouched ports are left as-is.

| Argument            | Type                 | Description                                             |
|---------------------|----------------------|---------------------------------------------------------|
| `device`            | `UnifiDevice \| str` | A `UnifiDevice` or its `_id`                            |
| `port_modes`        | `dict[int, str]`     | Map of `port_idx` → PoE mode (`"auto"`, `"off"`, …)     |
| `current_overrides` | `list[dict] \| list[PortOverride] \| None` | Existing overrides; if omitted they are taken from `device` or re-fetched |

```python
# Turn PoE off on ports 3 and 5 — just pass the device, overrides are handled
switch = unifi.find_device("office-switch")
unifi.set_port_poe(switch, {3: "off", 5: "off"})
```

> PoE modes: `"auto"` enables controller-negotiated PoE ("on"), `"off"` disables it.

### `cycle_port_poe(device, port_idxs, *, delay=5.0, restore_mode="auto") -> None`

Power-cycle PoE on one or more ports: turn them off, wait `delay` seconds, then
restore them (re-fetching the device so the restore merges cleanly). Handy for
rebooting a stuck PoE camera or AP.

```python
switch = unifi.find_device("office-switch")
unifi.cycle_port_poe(switch, [3, 5], delay=5)
```

### Lifecycle methods

- `login()` — authenticate (legacy/credential auth only)
- `logout()` — end the session (best-effort; never raises)
- `close()` — close the underlying HTTP connection

Using the client as a context manager handles all three for you.

## Error handling

The library raises its own exceptions, so callers never have to import or know
about `httpx`. All of them subclass `UnifiError`:

| Exception              | Raised when                                                |
|------------------------|------------------------------------------------------------|
| `UnifiAuthError`       | Login failed, or a request returned `401`/`403`            |
| `UnifiConnectionError` | The controller was unreachable (refused, timeout, DNS, TLS)|
| `UnifiAPIError`        | The controller returned another non-success status (`.status_code`) |
| `UnifiError`           | Base class — catch this to handle any of the above         |

```python
from matonb_unifi import UnifiClient, UnifiAuthError, UnifiError

try:
    with UnifiClient("https://192.168.1.1", api_key="bad-key") as unifi:
        unifi.get_clients()
except UnifiAuthError:
    print("Check your API key")
except UnifiError as exc:
    print(f"UniFi request failed: {exc}")
```

## Development

```bash
# Run the test suite
uv run --extra test pytest

# Lint and format
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .

# Type-check (strict)
uv run --extra typecheck mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow, including the
Conventional Commits convention used for automated releases.

## License

[MIT](LICENSE)
