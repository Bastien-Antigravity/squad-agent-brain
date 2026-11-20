#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
QA Engineer agent daemon specialized in verifying logic implementation, auditing unit tests,
probing internal service health/contracts endpoints safely, and reporting verification reports.

DATA FLOW:
1. Inherits BaseAgent initialization with role-specific prompt and event bus.
2. Registers run_squad_tests and SSRF-safe probe_service_health tools.
3. Validates probe URLs strictly against internal loopback/container DNS allowlists before querying.

KEY PARAMETERS:
- config: Application configuration singleton.
- logger: UniLog logging handle.
- pg_pool: Shared database connection pool.
- event_bus: SquadEventBus pub/sub provider.
"""

from asyncio import to_thread as asyncioToThread
from ipaddress import ip_address as ipaddressIpAddress
from re import match as reMatch
from typing import Any as typeAny, Dict as typeDict, Optional as typeOptional, Tuple as typeTuple
from urllib.error import HTTPError as urllibErrorHTTPError, URLError as urllibErrorURLError
from urllib.parse import urlparse as urllibParseUrlparse
from urllib.request import Request as urllibRequestRequest, urlopen as urllibRequestUrlopen

from src.interfaces import SquadEventBus
from src.agents.base_agent import BaseAgent

# -----------------------------------------------------------------------------------------------

_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "127.0.0.2"})
_MAX_RESPONSE_BYTES = 8192

# -----------------------------------------------------------------------------------------------


def run_squad_tests(test_command: str) -> str:
    """
    Runs the specified unit or integration test suite in the workspace.

    Args:
        test_command: The CLI command to run tests (e.g. 'pytest src/tests' or 'go test ./...').
    """
    return ""


# -----------------------------------------------------------------------------------------------


def probe_service_health(url: str, timeout_sec: float = 5.0) -> str:
    """
    Safely probes an internal service HTTP(S) endpoint (e.g. /api/v1/health, /api/v1/contracts,
    or web-interface /api/v1/services) using an SSRF-safe allowlist (127.0.0.1, 127.0.0.2,
    or single-label container DNS hosts).

    Args:
        url: Target internal service URL.
        timeout_sec: Request timeout in seconds (clamped between 1.0 and 15.0).
    """
    return ""


# -----------------------------------------------------------------------------------------------


def _validate_internal_probe_url(raw_url: str) -> typeTuple[bool, str]:
    """Enforces strict SSRF allowlist permitting only 127.0.0.1, 127.0.0.2, or single-label container DNS."""
    cleaned = (raw_url or "").strip()
    if not cleaned:
        return False, "Error: 'url' is required for probe_service_health."

    parsed = urllibParseUrlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Error: Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed."

    if parsed.username or parsed.password:
        return False, "Error: Embedded credentials in probe URL are prohibited."

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "Error: Missing hostname in probe URL."

    if hostname in _ALLOWED_LOOPBACK_HOSTS:
        return True, cleaned

    # Reject raw IP addresses outside 127.0.0.1 / 127.0.0.2
    try:
        ipaddressIpAddress(hostname)
    except ValueError:
        is_ip_literal = False
    else:
        is_ip_literal = True
    if is_ip_literal:
        return False, f"Error: External or disallowed IP '{hostname}' rejected by SSRF allowlist."

    # Allow single-label container DNS hosts only (no dots, must contain at least one letter)
    if "." in hostname or ":" in hostname:
        return False, f"Error: Multi-label external host '{hostname}' rejected by SSRF allowlist."
    if not reMatch(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", hostname) or not any(ch.isalpha() for ch in hostname):
        return False, f"Error: Invalid container DNS host '{hostname}' rejected by SSRF allowlist."

    return True, cleaned


# -----------------------------------------------------------------------------------------------


def _perform_http_probe(url: str, timeout_val: float) -> str:
    """Executes the synchronous HTTP GET probe inside a worker thread."""
    req = urllibRequestRequest(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllibRequestUrlopen(req, timeout=timeout_val) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
            return f"HTTP {status}\n{body}"
    except urllibErrorHTTPError as http_err:
        err_body = http_err.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        return f"HTTP {http_err.code}\n{err_body}"
    except urllibErrorURLError as url_err:
        return f"Error: Probe connection failed for '{url}': {url_err.reason}"


# -----------------------------------------------------------------------------------------------


class QAAgent(BaseAgent):
    """
    QA Engineer agent daemon. Specialised in verifying logic implementation,
    auditing unit tests, probing internal endpoints, and reporting verification reports.
    """

    def __init__(
        self,
        *,
        config: typeAny,
        logger: typeAny,
        pg_pool: typeAny,
        event_bus: SquadEventBus,
        target_brain_id: typeOptional[str] = None,
    ):
        super().__init__(
            role_name="qa",
            prompt_file="04-QA/Prompt-QA.md",
            config=config,
            logger=logger,
            pg_pool=pg_pool,
            event_bus=event_bus,
            target_brain_id=target_brain_id,
        )
        self.tools = self.tools + [run_squad_tests, probe_service_health]

    # -----------------------------------------------------------------------------------------------

    async def execute_tool(self, name: str, args: typeDict[str, typeAny]) -> str:
        """Executes a function call requested by the model."""
        if name == "run_squad_tests":
            cmd_arg = args.get("test_command", "")
            return await super().execute_tool("execute_shell_command", {"command": cmd_arg})

        if name == "probe_service_health":
            raw_url = str(args.get("url", ""))
            is_allowed, detail = _validate_internal_probe_url(raw_url)
            if not is_allowed:
                return detail

            try:
                raw_timeout = float(args.get("timeout_sec", 5.0))
            except (TypeError, ValueError):
                raw_timeout = 5.0
            timeout_val = max(1.0, min(15.0, raw_timeout))

            try:
                return await asyncioToThread(_perform_http_probe, detail, timeout_val)
            except Exception as exc:
                self.logger.warning(f"{self.Name} : probe_service_health failed for '{detail}': {exc}")
                return f"Error probing '{detail}': {exc}"

        return await super().execute_tool(name, args)
