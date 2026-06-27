"""Exception hierarchy raised by :mod:`matonb_unifi`."""

from __future__ import annotations


class UnifiError(Exception):
    """Base class for every error raised by matonb-unifi.

    Catching ``UnifiError`` catches all of the library's failures without
    importing ``httpx`` or knowing its exception hierarchy.
    """


class UnifiAuthError(UnifiError):
    """Authentication failed: bad credentials, API key, or expired session."""


class UnifiConnectionError(UnifiError):
    """The controller could not be reached (refused, timed out, DNS, TLS)."""


class UnifiAPIError(UnifiError):
    """The controller returned an unexpected, non-success HTTP status."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
