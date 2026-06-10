"""Generate the raster home-screen / favicon assets from the brand radar glyph.

Run once whenever the brand mark or its colours change; the PNG/ICO outputs are
committed to ``scripts/assets/`` and copied verbatim into the site at build time
(see ``build_site.write_site_extras``), so the 12-hourly box build needs no image
toolchain. Renders the exact ``FAVICON_SVG`` (single source of truth) with headless
Chromium so the icons match the browser-tab glyph pixel-for-pixel.

    python scripts/gen_icons.py    # needs: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import io
import os

from PIL import Image
from playwright.sync_api import sync_playwright

from build_site import FAVICON_SVG  # run as: python scripts/gen_icons.py

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# iOS / Android apply their own corner mask, so those tiles must bleed the accent
# to every edge (rx=0); the browser-tab favicon keeps its rounded square (rx=14).
_SQUARE_SVG = FAVICON_SVG.replace('rx="14"', 'rx="0"')


def _render(svg: str, size: int) -> Image.Image:
    """Render an SVG to a ``size``x``size`` RGBA PNG with headless Chromium."""
    sized = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    html = ("<!doctype html><meta charset=utf-8>"
            "<style>*{margin:0;padding:0}html,body{background:transparent}</style>"
            + sized)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size},
                                device_scale_factor=1)
        page.set_content(html)
        png = page.screenshot(omit_background=True,
                              clip={"x": 0, "y": 0, "width": size, "height": size})
        browser.close()
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    apple = _render(_SQUARE_SVG, 180)        # iOS rounds the square itself
    apple.save(os.path.join(ASSETS, "apple-touch-icon.png"))
    apple.save(os.path.join(ASSETS, "apple-touch-icon-precomposed.png"))
    _render(_SQUARE_SVG, 192).save(os.path.join(ASSETS, "icon-192.png"))
    _render(_SQUARE_SVG, 512).save(os.path.join(ASSETS, "icon-512.png"))
    _render(FAVICON_SVG, 64).save(os.path.join(ASSETS, "favicon.ico"),
                                  sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"wrote icon assets to {ASSETS}")


if __name__ == "__main__":
    main()
