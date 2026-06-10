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
    return _shoot(html, size, size, omit_background=True)


def _shoot(html: str, w: int, h: int, omit_background: bool = False) -> Image.Image:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h},
                                device_scale_factor=1)
        page.set_content(html)
        png = page.screenshot(omit_background=omit_background,
                              clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()
    return Image.open(io.BytesIO(png)).convert("RGBA")


# 1200x630 Open Graph / Twitter card banner (Pro-dark). Twitter/X cannot render
# SVG card images, so the social preview must be this PNG. The badge reuses the
# favicon glyph for brand continuity.
_BADGE = FAVICON_SVG.replace("<svg ", '<svg width="92" height="92" ', 1)
_OG_HTML = f"""<!doctype html><meta charset=utf-8>
<style>
 *{{margin:0;padding:0;box-sizing:border-box}}
 html,body{{width:1200px;height:630px}}
 body{{background:#000;color:#f5f5f7;position:relative;overflow:hidden;padding:84px;
   display:flex;flex-direction:column;justify-content:space-between;
   font-family:-apple-system,'Segoe UI',system-ui,Roboto,Helvetica,Arial,sans-serif}}
 .glow{{position:absolute;top:-280px;right:-220px;width:820px;height:820px;
   background:radial-gradient(circle,rgba(41,151,255,.30),rgba(41,151,255,0) 62%)}}
 .eyebrow{{color:#2997ff;font-weight:600;font-size:27px;letter-spacing:.2em;text-transform:uppercase}}
 h1{{font-size:90px;line-height:1.03;font-weight:700;letter-spacing:-.025em;margin-top:24px;max-width:1000px}}
 p{{color:#a1a1a6;font-size:35px;line-height:1.36;margin-top:30px;max-width:960px}}
 .foot{{display:flex;align-items:center;gap:24px;position:relative}}
 .badge{{width:92px;height:92px;border-radius:22px}}
 .url{{font-size:36px;font-weight:600}}
 .src{{color:#86868b;font-size:25px;margin-left:auto}}
</style>
<div class="glow"></div>
<div>
 <div class="eyebrow">Washington DC Metro</div>
 <h1>Every AI &amp; frontier-tech event in DC.</h1>
 <p>Think tanks, universities, the builder scene, and Congress. Deduped, ranked, and free to subscribe as a calendar.</p>
</div>
<div class="foot">
 {_BADGE}
 <span class="url">events.emersus.ai</span>
 <span class="src">Think tanks &middot; Universities &middot; Builders &middot; Congress</span>
</div>"""


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    apple = _render(_SQUARE_SVG, 180)        # iOS rounds the square itself
    apple.save(os.path.join(ASSETS, "apple-touch-icon.png"))
    apple.save(os.path.join(ASSETS, "apple-touch-icon-precomposed.png"))
    _render(_SQUARE_SVG, 192).save(os.path.join(ASSETS, "icon-192.png"))
    _render(_SQUARE_SVG, 512).save(os.path.join(ASSETS, "icon-512.png"))
    _render(FAVICON_SVG, 64).save(os.path.join(ASSETS, "favicon.ico"),
                                  sizes=[(16, 16), (32, 32), (48, 48)])
    og = _shoot(_OG_HTML, 1200, 630).convert("RGB")  # opaque card image
    og.save(os.path.join(ASSETS, "og-image.png"))
    print(f"wrote icon assets to {ASSETS}")


if __name__ == "__main__":
    main()
