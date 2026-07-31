from __future__ import annotations

import json
import ssl
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from axio_fusion_api import network


def _capture_opener(monkeypatch):
    captured = {}

    class FakeOpener:
        def open(self, request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            return object()

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    monkeypatch.setattr(network.urllib.request, "build_opener", fake_build_opener)
    return captured


def _proxy_handler(captured):
    handlers = captured["handlers"]
    assert handlers
    handler = handlers[0]
    assert isinstance(handler, network.urllib.request.ProxyHandler)
    return handler


def test_default_policy_is_auto_with_local_10808_proxy(monkeypatch):
    for name in (
        "AXIO_FUSION_NETWORK_MODE",
        "AXIO_FUSION_SYSTEM_PROXY",
        "AXIO_FUSION_HTTP_PROXY",
        "AXIO_FUSION_USE_SYSTEM_PROXY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(network, "_proxy_listener_detected", lambda _url: False)

    summary = network.provider_proxy_runtime_summary()

    assert summary["mode"] == "auto"
    assert summary["configured"] is True
    assert summary["valid"] is True
    assert summary["listener_detected"] is False
    assert summary["selected_transport"] == "direct"
    assert summary["reason_code"] == "proxy_listener_not_detected"
    assert summary["system_proxy_default"] == "local_default"
    assert "127.0.0.1:10808" not in json.dumps(summary, ensure_ascii=False)


def test_auto_uses_proxy_when_configured_listener_is_present(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "auto")
    monkeypatch.setenv("AXIO_FUSION_SYSTEM_PROXY", "http://127.0.0.1:18080")
    monkeypatch.delenv("AXIO_FUSION_HTTP_PROXY", raising=False)
    monkeypatch.setattr(network, "_proxy_listener_detected", lambda _url: True)
    captured = _capture_opener(monkeypatch)

    network.build_network_opener().open("unused", timeout=1)

    assert _proxy_handler(captured).proxies == {
        "http": "http://127.0.0.1:18080",
        "https": "http://127.0.0.1:18080",
    }
    summary = network.provider_proxy_runtime_summary()
    assert summary["selected_transport"] == "proxy"
    assert summary["listener_detected"] is True
    assert "127.0.0.1:18080" not in json.dumps(summary, ensure_ascii=False)


def test_auto_without_listener_forces_direct_even_when_process_proxy_is_set(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "auto")
    monkeypatch.setenv("AXIO_FUSION_SYSTEM_PROXY", "http://127.0.0.1:18080")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:19090")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19090")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:19090")
    monkeypatch.setattr(network, "_proxy_listener_detected", lambda _url: False)
    captured = _capture_opener(monkeypatch)

    network.build_network_opener()

    assert _proxy_handler(captured).proxies == {}


def test_on_fails_closed_when_proxy_listener_is_unavailable(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "on")
    monkeypatch.setenv("AXIO_FUSION_SYSTEM_PROXY", "http://127.0.0.1:18080")
    monkeypatch.setattr(network, "_proxy_listener_detected", lambda _url: False)

    with pytest.raises(network.NetworkPolicyError) as exc_info:
        network.build_network_opener()

    assert exc_info.value.reason_code == "proxy_unavailable"


def test_off_bypasses_all_inherited_process_proxy_variables(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")
    monkeypatch.setenv("AXIO_FUSION_SYSTEM_PROXY", "http://invalid proxy")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:19090")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19090")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:19090")
    captured = _capture_opener(monkeypatch)

    network.build_network_opener()

    assert _proxy_handler(captured).proxies == {}
    summary = network.provider_proxy_runtime_summary()
    assert summary["mode"] == "off"
    assert summary["selected_transport"] == "direct"
    assert "invalid proxy" not in json.dumps(summary, ensure_ascii=False)


def test_invalid_explicit_mode_is_rejected_without_fallback(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "sometimes")

    with pytest.raises(network.NetworkPolicyError) as exc_info:
        network.build_network_opener()

    assert exc_info.value.reason_code == "network_mode_invalid"


def test_https_connection_reapplies_timeout_before_and_after_tls(monkeypatch):
    raw_socket = None
    wrapped_socket = None

    class FakeSocket:
        def __init__(self):
            self.timeouts = []

        def settimeout(self, value):
            self.timeouts.append(float(value))

    class FakeContext:
        verify_mode = ssl.CERT_NONE
        check_hostname = False

        def wrap_socket(self, sock, *, server_hostname):
            del server_hostname
            nonlocal wrapped_socket
            wrapped_socket = FakeSocket()
            assert sock is raw_socket
            return wrapped_socket

    def fake_http_connect(connection):
        nonlocal raw_socket
        raw_socket = FakeSocket()
        connection.sock = raw_socket

    monkeypatch.setattr(network.http.client.HTTPConnection, "connect", fake_http_connect)

    connection = network._DeadlineHTTPSConnection(
        "provider.invalid",
        timeout=1.25,
        context=FakeContext(),
    )
    connection.connect()

    assert len(raw_socket.timeouts) == 1
    assert 0.0 < raw_socket.timeouts[0] <= 1.25
    assert len(wrapped_socket.timeouts) == 1
    assert 0.0 < wrapped_socket.timeouts[0] <= 1.25


def test_https_connection_watchdog_closes_blocked_proxy_socket(monkeypatch):
    closed = threading.Event()

    class BlockingSocket:
        def close(self):
            closed.set()

    def fake_http_connect(connection):
        connection.sock = BlockingSocket()
        if not closed.wait(1.0):
            raise AssertionError("connect watchdog did not close the proxy socket")
        raise OSError("proxy tunnel deadline expired")

    monkeypatch.setattr(network.http.client.HTTPConnection, "connect", fake_http_connect)

    connection = network._DeadlineHTTPSConnection(
        "provider.invalid",
        timeout=0.03,
        context=ssl.create_default_context(),
    )
    started = time.monotonic()
    with pytest.raises(OSError, match="deadline"):
        connection.connect()

    assert closed.is_set()
    assert time.monotonic() - started < 0.5


def test_network_opener_installs_bounded_https_handler(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_NETWORK_MODE", "off")
    captured = _capture_opener(monkeypatch)

    network.build_network_opener()

    assert any(
        isinstance(handler, network._DeadlineHTTPSHandler)
        for handler in captured["handlers"]
    )
