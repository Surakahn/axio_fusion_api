"""Process-local outbound network policy for the standalone Fusion runtime.

The runtime never relies on urllib's implicit environment proxy selection.  A
single policy decision chooses either an explicit proxy opener or an empty
proxy mapping, which makes ``off`` and the direct branch of ``auto`` genuinely
independent from inherited ``HTTP_PROXY``/``HTTPS_PROXY``/``ALL_PROXY`` values.

Only the short-lived process may hold the configured proxy URL.  Public
summaries intentionally expose state and reason codes, never the URL itself.
"""

from __future__ import annotations

import errno
import http.client
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_SYSTEM_PROXY = "http://127.0.0.1:10808"
NETWORK_MODES = ("auto", "on", "off")
_LEGACY_HTTP_PROXY_ENV = "AXIO_FUSION_HTTP_PROXY"
_LEGACY_USE_SYSTEM_PROXY_ENV = "AXIO_FUSION_USE_SYSTEM_PROXY"

_PROXY_BYPASS_HOSTS_ENV = "AXIO_FUSION_PROXY_BYPASS_HOSTS"

# Per-host proxy bypass: hosts in this env var (comma-separated)
# always go DIRECT even when global proxy is auto/on.
_proxy_bypass_hosts_cache: tuple[str, ...] | None = None
_NETWORK_MODE_ENV = "AXIO_FUSION_NETWORK_MODE"
_SYSTEM_PROXY_ENV = "AXIO_FUSION_SYSTEM_PROXY"


def _set_connection_socket_timeout(sock: Any, timeout: Any) -> None:
    """Best-effortly apply a finite HTTP connection timeout to a socket."""

    if sock is None or timeout is None or timeout is socket._GLOBAL_DEFAULT_TIMEOUT:
        return
    try:
        bounded = float(timeout)
    except (TypeError, ValueError):
        return
    if bounded <= 0.0:
        return
    setter = getattr(sock, "settimeout", None)
    if not callable(setter):
        return
    try:
        setter(bounded)
    except (OSError, TypeError, ValueError):
        return


class NetworkPolicyError(RuntimeError):
    """A safe, machine-readable outbound network policy failure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = str(reason_code or "network_policy_failed")
        super().__init__(f"fusion_network_policy_failed:{self.reason_code}")


class _DeadlineResponseMixin:
    """Bound the response-header read that happens before urllib returns.

    The provider stream watchdog starts after ``opener.open`` returns.  A
    stalled upstream can block earlier in ``HTTPConnection.getresponse`` while
    waiting for the first response-header byte, so that watchdog cannot wake
    it.  Closing the connection socket from a daemon timer makes this phase
    obey the same request deadline without introducing a second request loop.
    """

    def getresponse(self):
        deadline_at = getattr(self, "_axio_request_deadline_at", None)
        timeout = _finite_connection_timeout(getattr(self, "timeout", None))
        if deadline_at is not None:
            timeout = _remaining_connection_timeout(deadline_at, timeout)
        if timeout is None:
            return super().getresponse()

        def expire_response_header_read() -> None:
            sock = getattr(self, "sock", None)
            if sock is None:
                return
            try:
                sock.close()
            except Exception:
                return

        watchdog = threading.Timer(max(0.001, timeout), expire_response_header_read)
        watchdog.daemon = True
        watchdog.start()
        try:
            return super().getresponse()
        finally:
            watchdog.cancel()


class _DeadlineHTTPConnection(_DeadlineResponseMixin, http.client.HTTPConnection):
    """HTTP connection with one deadline across connect and response headers."""

    def connect(self) -> None:
        timeout = _finite_connection_timeout(self.timeout)
        deadline_at = time.monotonic() + timeout if timeout is not None else None
        self._axio_request_deadline_at = deadline_at

        def expire_connection() -> None:
            sock = getattr(self, "sock", None)
            if sock is None:
                return
            try:
                sock.close()
            except Exception:
                return

        watchdog = None
        if timeout is not None:
            watchdog = threading.Timer(timeout, expire_connection)
            watchdog.daemon = True
            watchdog.start()
        try:
            self.sock = self._create_connection(
                (self.host, self.port),
                timeout,
                self.source_address,
            )
            try:
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError as exc:
                if exc.errno != errno.ENOPROTOOPT:
                    raise
            if self._tunnel_host:
                _set_connection_socket_timeout(
                    self.sock,
                    _remaining_connection_timeout(deadline_at, timeout),
                )
                self._tunnel()
            _set_connection_socket_timeout(
                self.sock,
                _remaining_connection_timeout(deadline_at, timeout),
            )
        finally:
            if watchdog is not None:
                watchdog.cancel()


class _DeadlineHTTPSConnection(_DeadlineResponseMixin, http.client.HTTPSConnection):
    """HTTPS connection that bounds the proxy tunnel's TLS handshake.

    ``urllib`` forwards its timeout to ``HTTPSConnection``.  A few local HTTP
    proxy and TLS combinations nevertheless leave the socket without that
    timeout immediately before ``SSLContext.wrap_socket``.  The handshake can
    then outlive the provider request deadline.  Reusing the stdlib HTTP
    connection setup and explicitly refreshing the socket timeout before and
    after TLS keeps the transport bounded without changing payload handling.
    """

    def connect(self) -> None:
        timeout = _finite_connection_timeout(self.timeout)
        deadline_at = time.monotonic() + timeout if timeout is not None else None
        self._axio_request_deadline_at = deadline_at

        def expire_connection() -> None:
            sock = getattr(self, "sock", None)
            if sock is None:
                return
            try:
                sock.close()
            except Exception:
                return

        watchdog = None
        if timeout is not None:
            watchdog = threading.Timer(timeout, expire_connection)
            watchdog.daemon = True
            watchdog.start()
        try:
            # Keep the socket visible to the watchdog before entering the
            # proxy tunnel. The stdlib implementation creates the socket and
            # enters ``_tunnel`` in one opaque call, which makes it difficult
            # to carry one deadline across TCP, CONNECT, and TLS reliably.
            self.sock = self._create_connection(
                (self.host, self.port),
                timeout,
                self.source_address,
            )
            try:
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError as exc:
                if exc.errno != errno.ENOPROTOOPT:
                    raise
            if self._tunnel_host:
                _set_connection_socket_timeout(
                    self.sock,
                    _remaining_connection_timeout(deadline_at, timeout),
                )
                # The tunnel reader is now bounded by both the socket timeout
                # and the watchdog, rather than an unbounded stdlib read.
                self._tunnel()
            remaining = _remaining_connection_timeout(deadline_at, timeout)
            _set_connection_socket_timeout(self.sock, remaining)
            server_hostname = self._tunnel_host or self.host
            self.sock = self._context.wrap_socket(
                self.sock,
                server_hostname=server_hostname,
            )
            # Some SSL wrappers reset the timeout while taking ownership of the
            # raw socket. Restore only the time that remains in this connect
            # deadline so CONNECT + TLS cannot exceed the original budget.
            _set_connection_socket_timeout(
                self.sock,
                _remaining_connection_timeout(deadline_at, timeout),
            )
        finally:
            if watchdog is not None:
                watchdog.cancel()


def _finite_connection_timeout(value: Any) -> float | None:
    if value is None or value is socket._GLOBAL_DEFAULT_TIMEOUT:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0.0 else None


def _remaining_connection_timeout(
    deadline_at: float | None,
    fallback: float | None,
) -> float | None:
    if deadline_at is None:
        return fallback
    return max(0.001, deadline_at - time.monotonic())


class _DeadlineHTTPSHandler(urllib.request.HTTPSHandler):
    """Use the bounded HTTPS connection for every provider HTTPS request."""

    def https_open(self, req):
        return self.do_open(
            _DeadlineHTTPSConnection,
            req,
            context=self._context,
            check_hostname=self._check_hostname,
        )


class _DeadlineHTTPHandler(urllib.request.HTTPHandler):
    """Use the bounded HTTP connection for direct and HTTP-proxy requests."""

    def http_open(self, req):
        return self.do_open(_DeadlineHTTPConnection, req)


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str
    proxy_url: str
    configured: bool
    valid: bool
    listener_detected: bool | None
    selected_transport: str
    reason_code: str
    source: str
    legacy_label: str = ""


def provider_proxy_readiness(value: Any) -> dict[str, Any]:
    """Validate an HTTP(S) proxy without returning its value."""

    raw = str(value or "").strip()
    result = {
        "schema": "axio_fusion_api.provider_proxy_readiness.v2",
        "configured": bool(raw),
        "valid": False,
        "reason_code": "proxy_missing",
        "raw_proxy_url_persisted": False,
        "secrets_persisted": False,
    }
    if not raw:
        return result
    if any(character.isspace() for character in raw):
        result["reason_code"] = "proxy_contains_whitespace"
        return result
    if "@" in raw:
        result["reason_code"] = "proxy_embedded_auth_not_allowed"
        return result
    if "?" in raw:
        result["reason_code"] = "proxy_query_not_allowed"
        return result
    if "#" in raw:
        result["reason_code"] = "proxy_fragment_not_allowed"
        return result
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        result["reason_code"] = "proxy_parse_failed"
        return result
    if parsed.scheme.lower() not in {"http", "https"}:
        result["reason_code"] = "proxy_scheme_not_allowed"
        return result
    if not parsed.netloc or not parsed.hostname:
        result["reason_code"] = "proxy_host_missing"
        return result
    if parsed.username or parsed.password:
        result["reason_code"] = "proxy_embedded_auth_not_allowed"
        return result
    if parsed.path not in {"", "/"}:
        result["reason_code"] = "proxy_path_not_allowed"
        return result
    try:
        port = parsed.port
    except ValueError:
        result["reason_code"] = "proxy_invalid_port"
        return result
    if port is not None and not 1 <= int(port) <= 65535:
        result["reason_code"] = "proxy_invalid_port"
        return result
    result["valid"] = True
    result["reason_code"] = ""
    return result


def resolve_network_policy(*, check_listener: bool = True) -> NetworkPolicy:
    """Resolve the current three-state network policy.

    ``AXIO_FUSION_NETWORK_MODE`` is authoritative when present.  The two old
    variables remain compatible for deployments that have not migrated yet:
    an old explicit proxy or ``USE_SYSTEM_PROXY=1`` means forced proxy mode;
    otherwise the new default is ``auto``.
    """

    raw_mode = os.getenv(_NETWORK_MODE_ENV, "").strip().casefold()
    legacy_explicit = os.getenv(_LEGACY_HTTP_PROXY_ENV, "").strip()
    legacy_system = _truthy_env(_LEGACY_USE_SYSTEM_PROXY_ENV)
    legacy_label = ""
    if raw_mode:
        mode = raw_mode
        source = "environment"
    elif legacy_explicit:
        mode = "on"
        source = "legacy_environment"
        legacy_label = "explicit"
    elif legacy_system:
        mode = "on"
        source = "legacy_environment"
        legacy_label = "system_10808"
    else:
        mode = "auto"
        source = "default"

    proxy_url, proxy_source = _configured_proxy_url(legacy_explicit=legacy_explicit)
    if raw_mode and mode not in NETWORK_MODES:
        return NetworkPolicy(
            mode=mode,
            proxy_url=proxy_url,
            configured=bool(proxy_url),
            valid=False,
            listener_detected=None,
            selected_transport="error",
            reason_code="network_mode_invalid",
            source=source,
        )

    readiness = provider_proxy_readiness(proxy_url)
    valid = readiness["valid"] is True
    if mode == "off":
        return NetworkPolicy(
            mode=mode,
            proxy_url=proxy_url,
            configured=readiness["configured"] is True,
            valid=valid,
            listener_detected=None,
            selected_transport="direct",
            reason_code="network_mode_off",
            source=source,
            legacy_label=legacy_label,
        )

    if not valid:
        return NetworkPolicy(
            mode=mode,
            proxy_url=proxy_url,
            configured=readiness["configured"] is True,
            valid=False,
            listener_detected=False,
            selected_transport="direct" if mode == "auto" else "error",
            reason_code=(
                "proxy_invalid_auto_direct" if mode == "auto" else readiness["reason_code"]
            ),
            source=source,
            legacy_label=legacy_label,
        )

    listener_detected = _proxy_listener_detected(proxy_url) if check_listener else None
    if listener_detected is True:
        return NetworkPolicy(
            mode=mode,
            proxy_url=proxy_url,
            configured=True,
            valid=True,
            listener_detected=True,
            selected_transport="proxy",
            reason_code="proxy_listener_detected",
            source=source if source != "default" else f"{source}:{proxy_source}",
            legacy_label=legacy_label,
        )
    return NetworkPolicy(
        mode=mode,
        proxy_url=proxy_url,
        configured=True,
        valid=True,
        listener_detected=False,
        selected_transport="direct" if mode == "auto" else "error",
        reason_code="proxy_listener_not_detected",
        source=source if source != "default" else f"{source}:{proxy_source}",
        legacy_label=legacy_label,
    )


def provider_proxy_runtime_summary() -> dict[str, Any]:
    """Return a secret-free snapshot of the selected network transport."""

    policy = resolve_network_policy()
    bypass_hosts = _resolve_proxy_bypass_hosts()
    return {
        "schema": "axio_fusion_api.provider_proxy_runtime.v2",
        "mode": policy.legacy_label or policy.mode,
        "proxy_bypass_host_count": len(bypass_hosts),
        "configured": policy.configured,
        "valid": policy.valid,
        "listener_detected": policy.listener_detected,
        "selected_transport": policy.selected_transport,
        "reason_code": policy.reason_code,
        "source": policy.source,
        "system_proxy_default": "local_default" if policy.proxy_url == DEFAULT_SYSTEM_PROXY else "",
        "raw_proxy_url_persisted": False,
        "secrets_persisted": False,
    }



class _BypassProxyHandler(urllib.request.ProxyHandler):
    """ProxyHandler that skips the proxy for configured bypass hosts."""

    def __init__(self, proxies, *, bypass_hosts=()):
        super().__init__(proxies)
        self._bypass_hosts = frozenset(
            host.strip().casefold()
            for host in bypass_hosts
            if host.strip()
        )

    def proxy_open(self, req, proxy, type_):
        hostname = urllib.parse.urlsplit(req.get_full_url()).hostname
        if hostname and hostname.casefold() in self._bypass_hosts:
            return None  # urllib interprets None as "no proxy for this request"
        return super().proxy_open(req, proxy, type_)


def _resolve_proxy_bypass_hosts() -> tuple[str, ...]:
    """Return configured proxy bypass hosts, cached for the process lifetime."""
    global _proxy_bypass_hosts_cache
    if _proxy_bypass_hosts_cache is not None:
        return _proxy_bypass_hosts_cache
    raw = os.getenv(_PROXY_BYPASS_HOSTS_ENV, "").strip()
    hosts: list[str] = []
    for part in raw.split(","):
        host = part.strip().casefold()
        if host:
            hosts.append(host)
    _proxy_bypass_hosts_cache = tuple(hosts)
    return _proxy_bypass_hosts_cache
class _UserAgentHandler(urllib.request.BaseHandler):
    """Inject a plain User-Agent header so Cloudflare-protected upstreams
    (TokenAPIs and similar) do not return 403/1010 blocks."""

    def http_request(self, req):
        req.add_header("User-Agent", "AxioFusionAPI/1.0")
        return req

    https_request = http_request



def build_network_opener(*handlers: Any):
    """Build an opener whose proxy behavior is fully determined by policy."""

    policy = resolve_network_policy()
    if policy.reason_code == "network_mode_invalid":
        raise NetworkPolicyError("network_mode_invalid")
    if policy.selected_transport == "error":
        raise NetworkPolicyError("proxy_unavailable")
    if policy.selected_transport == "proxy":
        proxy_handler = urllib.request.ProxyHandler(
            {"http": policy.proxy_url, "https": policy.proxy_url}
        )
    else:
        # An empty mapping is required.  Calling urllib.request.urlopen() would
        # re-read inherited proxy environment variables and violate ``off`` or
        # the direct branch of ``auto``.
        proxy_handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(
        proxy_handler,
        _UserAgentHandler(),
        _DeadlineHTTPHandler(),
        _DeadlineHTTPSHandler(),
        *tuple(handlers),
    )


def _configured_proxy_url(*, legacy_explicit: str) -> tuple[str, str]:
    if legacy_explicit:
        return legacy_explicit, "legacy_explicit"
    if _SYSTEM_PROXY_ENV in os.environ:
        return os.getenv(_SYSTEM_PROXY_ENV, "").strip(), "configured_system_proxy"
    return DEFAULT_SYSTEM_PROXY, "default_system_proxy"


def _proxy_listener_detected(proxy_url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(proxy_url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
        if not hostname or not 1 <= int(port) <= 65535:
            return False
        timeout = _proxy_detection_timeout()
        with socket.create_connection((hostname, int(port)), timeout=timeout):
            return True
    except (OSError, TypeError, ValueError):
        return False


def _proxy_detection_timeout() -> float:
    raw = os.getenv("AXIO_FUSION_PROXY_DETECTION_TIMEOUT_SECONDS", "0.25").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.25
    return max(0.05, min(2.0, value))


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}
