import json
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


def test_write_site_extras_writes_full_icon_set(tmp_path):
    # iOS (apple-touch-icon + favicon.ico) and Android (manifest + 192/512 png)
    # home-screen / tab icons, so the root-probe 404s go away across platforms.
    d = str(tmp_path / "site")
    write_site_extras(d, "2026-05-30")
    for name in ("favicon.ico", "apple-touch-icon.png",
                 "apple-touch-icon-precomposed.png", "icon-192.png",
                 "icon-512.png", "site.webmanifest"):
        p = os.path.join(d, name)
        assert os.path.exists(p), f"missing {name}"
        assert os.path.getsize(p) > 0, f"empty {name}"
    with open(os.path.join(d, "apple-touch-icon.png"), "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    with open(os.path.join(d, "favicon.ico"), "rb") as f:
        assert f.read(4) == b"\x00\x00\x01\x00"  # ICO magic


def test_webmanifest_references_android_icons(tmp_path):
    d = str(tmp_path / "site")
    write_site_extras(d, "2026-05-30")
    with open(os.path.join(d, "site.webmanifest"), encoding="utf-8") as f:
        manifest = json.load(f)
    srcs = {icon["src"] for icon in manifest["icons"]}
    assert "/icon-192.png" in srcs and "/icon-512.png" in srcs


def test_favicon_uses_dark_palette_accent(tmp_path):
    d = str(tmp_path / "site")
    write_site_extras(d, "2026-05-30")
    with open(os.path.join(d, "favicon.svg"), encoding="utf-8") as f:
        svg = f.read()
    assert "#1a4fd0" not in svg          # old pre-redesign blue gone
    assert "#2997ff" in svg              # Pro-dark accent


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
