import os

from scripts.build_site import (
    DOMAIN,
    _heartbeat,
    _site_dir,
    write_site_extras,
)


def test_domain_is_the_subdomain():
    assert DOMAIN == "events.emersus.ai"


def test_site_dir_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("SITE_DIR", raising=False)
    assert _site_dir() == "site"
    monkeypatch.setenv("SITE_DIR", "/var/www/events.emersus.ai")
    assert _site_dir() == "/var/www/events.emersus.ai"


def test_write_site_extras_writes_favicon(tmp_path):
    # index.html + feeds are written by the pipeline (aggregator.web.render_index);
    # write_site_extras owns the favicon (+ credentials when present).
    d = str(tmp_path / "site")
    write_site_extras(d, "2026-05-30")
    assert os.path.exists(os.path.join(d, "favicon.svg"))


def test_heartbeat_noop_without_url(monkeypatch):
    # No HEALTHCHECK_URL set -> no ping attempted, returns False, never raises.
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    assert _heartbeat() is False


def test_heartbeat_pings_configured_url(monkeypatch):
    calls = []
    monkeypatch.setattr("scripts.build_site.urllib.request.urlopen",
                        lambda url, timeout=10: calls.append(url))
    assert _heartbeat("https://hc.example/ping/abc") is True
    assert calls == ["https://hc.example/ping/abc"]


def test_heartbeat_swallows_errors(monkeypatch):
    def boom(url, timeout=10):
        raise OSError("network down")
    monkeypatch.setattr("scripts.build_site.urllib.request.urlopen", boom)
    # Best-effort: a failed ping must not raise and must report False.
    assert _heartbeat("https://hc.example/ping/abc") is False
