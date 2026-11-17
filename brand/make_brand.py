"""Generates the Freakyyy brand kit (SVG masters, PNGs, Windows .ico, Android vector icon).

Concept: a geometric "F" whose middle arm ends in the AI core (the "eye"),
encircled by an orbital energy ring with one orbiting node. Monoline geometry,
readable at 16 px and without any glow.

Run:  desktop\\.venv\\Scripts\\python brand\\make_brand.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

BLACK, NAVY, BLUE, CYAN, WHITE = "#080B12", "#0B1424", "#168BFF", "#42D9FF", "#F5F8FF"

# ---------------------------------------------------------------- geometry (512 x 512)
# Orbital ring: a 300-degree arc with a gap at the upper right, plus one node.
RING = "M 390.4 160.0 A 168 168 0 1 1 323.0 101.9"       # r=168 around (256,256)
NODE = (390.4, 160.0)
# Geometric F: stem + top arm, and a middle arm that runs into the AI core.
D = "M 330 152 L 196 152 L 196 360 M 196 250 L 258 250"
CORE_C = (300, 250)


def emblem_svg(ring, d, core_outer, core_inner, node, *, glow=False, bg=None, scale=1.0, simple=False) -> str:
    defs = ""
    core_fill = core_outer
    if core_outer == "grad":
        defs += (f'<radialGradient id="core" cx="45%" cy="40%" r="60%"><stop offset="0" stop-color="{WHITE}"/>'
                 f'<stop offset="0.35" stop-color="{CYAN}"/><stop offset="1" stop-color="{BLUE}"/></radialGradient>')
        core_fill = "url(#core)"
    if glow:
        defs += ('<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9" result="b"/>'
                 '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    g = ' filter="url(#glow)"' if glow else ""
    t = f' transform="translate(256 256) scale({scale}) translate(-256 -256)"' if scale != 1 else ""
    sw_ring, sw_d = (22, 30) if simple else (14, 26)
    parts = [f'<path d="{RING}" fill="none" stroke="{ring}" stroke-width="{sw_ring}" stroke-linecap="round"/>']
    if node:
        parts.append(f'<circle cx="{NODE[0]}" cy="{NODE[1]}" r="{18 if simple else 13}" fill="{node}"/>')
    parts.append(f'<path d="{D}" fill="none" stroke="{d}" stroke-width="{sw_d}" stroke-linejoin="round" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{CORE_C[0]}" cy="{CORE_C[1]}" r="{46 if simple else 40}" fill="{core_fill}"/>')
    if core_inner and not simple:
        parts.append(f'<circle cx="{CORE_C[0]}" cy="{CORE_C[1]}" r="15" fill="none" stroke="{core_inner}" stroke-width="7"/>')
    bgrect = ""
    if bg:
        defs += (f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{NAVY}"/>'
                 f'<stop offset="1" stop-color="{BLACK}"/></linearGradient>')
        bgrect = '<rect x="0" y="0" width="512" height="512" rx="112" fill="url(#bg)"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<defs>{defs}</defs>{bgrect}<g{g}{t}>{"".join(parts)}</g></svg>')


# ---------------------------------------------------------------- wordmark (geometric monoline letters)
LETTERS = {
    "F": ("M64 0 H0 V100 M0 50 H52", 64),
    "A": ("M0 100 L38 0 L76 100 M15 62 H61", 76),
    "K": ("M0 0 V100 M68 0 L8 56 M28 38 L72 100", 72),
    "Y": ("M0 0 L36 52 L72 0 M36 52 V100", 72),
    "D": ("M0 0 V100 H38 A50 50 0 0 0 38 0 Z", 88),
    "E": ("M64 0 H0 V100 H64 M0 50 H52", 64),
    "X": ("M0 0 L76 100 M76 0 L0 100", 76),
    "T": ("M0 0 H72 M36 0 V100", 72),
    "R": ("M0 100 V0 H42 A27 27 0 0 1 42 54 H0 M38 54 L72 100", 72),
}


def wordmark_svg(color: str, with_emblem: bool = False) -> str:
    x = 0.0
    paths = []
    for ch in "FREAKYYY":
        d, w = LETTERS[ch]
        paths.append(f'<path transform="translate({x:.1f} 0)" d="{d}"/>')
        x += w + 36
    width = x - 36
    body = (f'<g fill="none" stroke="{color}" stroke-width="10" stroke-linecap="square" stroke-linejoin="miter" '
            f'transform="translate({170 if with_emblem else 10} 30)">{"".join(paths)}</g>')
    emblem = ""
    if with_emblem:
        emblem = (f'<g transform="translate(0 0) scale(0.3125)">'
                  + emblem_svg(BLUE, color, "grad", BLACK, CYAN).split('<g>', 1)[1].rsplit('</g>', 1)[0]
                  + "</g>")
        defs = ('<defs><radialGradient id="core" cx="45%" cy="40%" r="60%"><stop offset="0" stop-color="#F5F8FF"/>'
                '<stop offset="0.35" stop-color="#42D9FF"/><stop offset="1" stop-color="#168BFF"/></radialGradient></defs>')
        emblem = defs + emblem
    total_w = width + (180 if with_emblem else 20)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} 160" width="{total_w:.0f}" height="160">'
            f'{emblem}{body}</svg>')


VARIANTS = {
    "freakyyy-emblem-full.svg": emblem_svg(BLUE, WHITE, "grad", BLACK, CYAN),
    "freakyyy-emblem-glow.svg": emblem_svg(CYAN, WHITE, "grad", BLACK, CYAN, glow=True),
    "freakyyy-emblem-white.svg": emblem_svg(WHITE, WHITE, WHITE, BLACK, WHITE),
    "freakyyy-emblem-black.svg": emblem_svg(BLACK, BLACK, BLACK, WHITE, BLACK),
    "freakyyy-app-icon.svg": emblem_svg(BLUE, WHITE, "grad", BLACK, CYAN, bg=True, scale=0.78, simple=True),
    "freakyyy-island-emblem.svg": emblem_svg(CYAN, WHITE, CYAN, None, None, simple=True),
    "freakyyy-wordmark-white.svg": wordmark_svg(WHITE),
    "freakyyy-wordmark-black.svg": wordmark_svg(BLACK),
    "freakyyy-lockup-white.svg": wordmark_svg(WHITE, with_emblem=True),
}


def render(svg_text: str, size: int, path: Path, width: int | None = None):
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    r = QSvgRenderer(QByteArray(svg_text.encode()))
    vb = r.viewBoxF()
    h = size
    w = width or round(size * vb.width() / vb.height())
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, w, h))
    p.end()
    img.save(str(path))


def android_vector() -> str:
    """Adaptive-icon foreground (108dp canvas, emblem inside the 66dp safe zone)."""
    s = 66 / 512 * 0.92
    off = (108 - 512 * s) / 2
    return f'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">
    <group android:translateX="{off:.3f}" android:translateY="{off:.3f}" android:scaleX="{s:.5f}" android:scaleY="{s:.5f}">
        <path android:pathData="{RING}" android:strokeColor="{BLUE}" android:strokeWidth="22" android:strokeLineCap="round" android:fillColor="#00000000"/>
        <path android:pathData="M{NODE[0] - 18},{NODE[1]} a18,18 0 1,0 36,0 a18,18 0 1,0 -36,0" android:fillColor="{CYAN}"/>
        <path android:pathData="{D}" android:strokeColor="{WHITE}" android:strokeWidth="30" android:strokeLineJoin="round" android:strokeLineCap="round" android:fillColor="#00000000"/>
        <path android:pathData="M{CORE_C[0] - 46},{CORE_C[1]} a46,46 0 1,0 92,0 a46,46 0 1,0 -92,0" android:fillColor="{CYAN}"/>
    </group>
</vector>
'''


ANDROID_BG = f'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">
    <path android:pathData="M0,0h108v108h-108z">
        <aapt:attr xmlns:aapt="http://schemas.android.com/aapt" name="android:fillColor">
            <gradient android:type="linear" android:startX="54" android:startY="0" android:endX="54" android:endY="108">
                <item android:offset="0" android:color="{NAVY}"/>
                <item android:offset="1" android:color="{BLACK}"/>
            </gradient>
        </aapt:attr>
    </path>
</vector>
'''


def main():
    for name, svg in VARIANTS.items():
        (OUT / name).write_text(svg, encoding="utf-8")
    render(VARIANTS["freakyyy-emblem-full.svg"], 1024, OUT / "freakyyy-emblem-full-1024.png")
    render(VARIANTS["freakyyy-emblem-glow.svg"], 1024, OUT / "freakyyy-emblem-glow-1024.png")
    render(VARIANTS["freakyyy-emblem-white.svg"], 1024, OUT / "freakyyy-emblem-white-1024.png")
    render(VARIANTS["freakyyy-emblem-black.svg"], 1024, OUT / "freakyyy-emblem-black-1024.png")
    render(VARIANTS["freakyyy-app-icon.svg"], 1024, OUT / "freakyyy-app-icon-1024.png")
    render(VARIANTS["freakyyy-island-emblem.svg"], 256, OUT / "freakyyy-island-emblem-256.png")
    render(VARIANTS["freakyyy-lockup-white.svg"], 320, OUT / "freakyyy-lockup-white.png")
    render(VARIANTS["freakyyy-wordmark-white.svg"], 200, OUT / "freakyyy-wordmark-white.png")
    render(VARIANTS["freakyyy-wordmark-black.svg"], 200, OUT / "freakyyy-wordmark-black.png")

    # Windows .ico: the simplified app icon at every standard size.
    from PIL import Image
    big = Image.open(OUT / "freakyyy-app-icon-1024.png").convert("RGBA")
    big.save(OUT / "freakyyy.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # Desktop app + Android launcher.
    root = HERE.parent
    (root / "desktop" / "freakyyy" / "ui" / "assets").mkdir(parents=True, exist_ok=True)
    for f in ("freakyyy-app-icon.svg", "freakyyy-island-emblem.svg", "freakyyy-emblem-full.svg"):
        (root / "desktop" / "freakyyy" / "ui" / "assets" / f).write_text(VARIANTS[f], encoding="utf-8")
    (root / "desktop" / "freakyyy.ico").write_bytes((OUT / "freakyyy.ico").read_bytes())
    res = root / "mobile" / "app" / "src" / "main" / "res" / "drawable"
    (res / "ic_launcher_foreground.xml").write_text(android_vector(), encoding="utf-8")
    (res / "ic_launcher_background.xml").write_text(ANDROID_BG, encoding="utf-8")
    print("Brand kit written to", OUT)


if __name__ == "__main__":
    main()
