"""Decide which IP addresses this personal app is willing to use.

The phone and the laptop must be on the same LAN. Public addresses are rejected
so a port-forward from the internet cannot open a session.
"""

from __future__ import annotations

import ipaddress


def is_allowed_host(host: str) -> bool:
    """True for RFC1918, link-local, and loopback addresses.

    Loopback is allowed so the protocol tests can run on this computer.
    It is not reachable from the internet.
    """
    try:
        ip = ipaddress.ip_address(host.strip())
    except ValueError:
        return False
    if ip.is_unspecified or ip.is_multicast:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def choose_host(addresses: list[str]) -> str | None:
    """Prefer a private IPv4 address from an mDNS result."""
    allowed = [addr for addr in addresses if is_allowed_host(addr)]
    for addr in allowed:
        if ":" not in addr:
            return addr
    return allowed[0] if allowed else None
