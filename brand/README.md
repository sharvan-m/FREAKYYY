# Freakyyy brand kit

**Concept:** a geometric **D** whose counter holds an **AI core**, encircled by an **orbital ring** with a single orbiting node.

- It reads as "intelligence that is always on and always around you". The core is the assistant, and the ring is its reach across your devices.
- The geometry is monoline and symmetrical around the core.
- It contains no robot faces, circuits or gaming cues, and it stays legible at 16 px without any glow.

**Palette**

| Color | Hex |
|---|---|
| Deep black | `#080B12` |
| Midnight navy | `#0B1424` |
| Electric blue | `#168BFF` |
| Cyan | `#42D9FF` |
| White | `#F5F8FF` |

**Wordmark:** the letters are drawn as geometric monoline paths in the SVG itself, so they don't depend on any installed font. They use wide tracking.

## Files (`out/`)

| Asset | SVG master | Raster |
|---|---|---|
| A · Primary emblem, full color | `freakyyy-emblem-full.svg` | `freakyyy-emblem-full-1024.png` |
| Blue/cyan glow | `freakyyy-emblem-glow.svg` | `freakyyy-emblem-glow-1024.png` |
| White monochrome | `freakyyy-emblem-white.svg` | `freakyyy-emblem-white-1024.png` |
| Black monochrome (documents) | `freakyyy-emblem-black.svg` | `freakyyy-emblem-black-1024.png` |
| B · Wordmark | `freakyyy-wordmark-white.svg`, `freakyyy-wordmark-black.svg` | `.png` |
| Lockup (emblem + wordmark) | `freakyyy-lockup-white.svg` | `freakyyy-lockup-white.png` |
| C · App icon (Windows/Android, simplified strokes) | `freakyyy-app-icon.svg` | `freakyyy-app-icon-1024.png`, `freakyyy.ico` (16–256 px) |
| D · Island emblem (tiny, simplified) | `freakyyy-island-emblem.svg` | `freakyyy-island-emblem-256.png` |

All PNGs have transparent backgrounds, except the app icon, which has a rounded navy tile.

**Where it's used**
- `desktop/freakyyy.ico`: the exe icon.
- `desktop/freakyyy/ui/assets/*.svg`: the window and tray icon (the tray adds a red dot while the mic is open).
- `mobile/.../res/drawable/ic_launcher_foreground.xml` and `ic_launcher_background.xml`: the Android adaptive launcher icon.

**Animated emblem:** `desktop/freakyyy/ui/emblem.py` draws the same geometry live:

| State | Animation |
|---|---|
| Idle | Breathing glow at 12 fps |
| Listening | Core follows the microphone level |
| Thinking | Ring rotates slowly |
| Executing | An energy pulse travels the ring |
| Speaking | Core pulses with the voice |
| Success | A brief flare |
| Error | Same mark in red |

Its timers stop while it's hidden.

To regenerate everything, including the app icons, run:

```bash
desktop\.venv\Scripts\python brand\make_brand.py
```
