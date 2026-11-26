"""0.2.0 Desk map: the graphics ladder and the three renderers (Kitty image, Braille, text table).

Ladder (App Design Template 1.0, as Dirlume 1.7.3 ``termgfx``): ``NUZEHUB_TUI_GRAPHICS`` (auto | kitty | braille |
text) first; for auto, Kitty graphics when ``remote.kitty_env()`` holds and the output is a terminal outside
tmux/screen; otherwise Braille; a plain text table when the output is not UTF-8. Environment only: the terminal is
never queried (textual-image's own probe is pre-empted). World outlines: world-atlas countries-110m (ISC, from Natural
Earth, public domain), cleaned as the web's geo-clean.ts does; see NOTICE.

Views: "tactical" is an orthographic globe centred on ``lon`` (Spin turns it), "flat" is an equirectangular map
centred on ``lon``. Layers follow globe-prefs.ts.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from rich.text import Text

from nuzehub_tui import rank, remote
from nuzehub_tui.themes import Palette, mix

EXCHANGES = ((40.757, -73.986), (40.707, -74.011), (41.878, -87.636), (51.515, -0.099), (35.683, 139.778),
             (22.284, 114.158), (25.033, 121.565), (50.115, 8.672), (48.869, 2.341), (52.374, 4.892), (47.37, 8.539),
             (43.648, -79.381), (-33.865, 151.209), (31.23, 121.473), (22.543, 114.058), (37.566, 126.978),
             (19.076, 72.878))  # exchanges.ts CITIES


# ---- detection ---------------------------------------------------------------------------------------------------


def is_ssh(env: Any = None) -> bool:
    e = os.environ if env is None else env
    return bool((e.get("SSH_CONNECTION") or "").strip() or (e.get("SSH_TTY") or "").strip())


def utf8(env: Any = None, encoding: str | None = None) -> bool:
    """Dirlume 1.7.3 ``remote.utf8``: the output stream's encoding when known, else the locale variables."""
    e = os.environ if env is None else env
    if encoding is None and env is None:
        encoding = getattr(sys.__stdout__, "encoding", None) if sys.__stdout__ else None
    if encoding:
        return encoding.replace("-", "").replace("_", "").lower() == "utf8"
    loc = e.get("LC_ALL") or e.get("LC_CTYPE") or e.get("LANG") or ""
    return "utf-8" in loc.lower() or "utf8" in loc.lower()


@dataclass
class Graphics:
    mode: str  # "kitty" | "braille" | "text"
    reason: str
    widget: type | None = None
    cell: tuple[int, int] = (10, 20)


def _winsize_cell() -> tuple[int, int]:
    try:
        import fcntl
        import struct
        import termios
        fd = sys.__stdout__.fileno() if sys.__stdout__ else -1
        rows, cols, xpx, ypx = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
        if rows and cols and xpx and ypx:
            return max(1, xpx // cols), max(1, ypx // rows)
    except Exception:  # noqa: BLE001 - no tty
        pass
    return (10, 20)


def _preset(tgp: bool, cell: tuple[int, int]) -> None:
    """Tell textual-image what the terminal can do so importing it never writes a probe (Dirlume 1.7.3)."""
    try:
        from textual_image import _terminal as tit
        tit.probe_terminal._result = tit.TerminalCapabilities(tit.CellSize(*cell), sixel=False, tgp=tgp)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - textual-image missing: Braille
        pass


def detect(env: Any = None, tty: bool | None = None) -> Graphics:
    e = os.environ if env is None else env
    want = (e.get("NUZEHUB_TUI_GRAPHICS") or "auto").strip().lower()
    tty = bool(sys.__stdout__ and sys.__stdout__.isatty()) if tty is None else tty
    cell = _winsize_cell() if tty else (10, 20)
    text_ok = utf8(env) if env is not None else utf8()
    where = "over SSH: " if is_ssh(e) else ""
    _preset(False, cell)
    if want == "text" or not text_ok:
        return Graphics("text", "forced by NUZEHUB_TUI_GRAPHICS=text" if want == "text" else where + "output is not UTF-8")
    if want == "braille":
        return Graphics("braille", "forced by NUZEHUB_TUI_GRAPHICS=braille")
    kitty_reason = ""
    if want == "kitty":
        kitty_reason = "forced by NUZEHUB_TUI_GRAPHICS=kitty"
    elif not tty:
        return Graphics("braille", where + "not a terminal")
    elif e.get("TMUX") or (e.get("TERM") or "").startswith(("screen", "tmux")):
        return Graphics("braille", where + "inside tmux/screen")
    elif remote.kitty_env(e):
        kitty_reason = where + "Kitty-graphics terminal"
    else:
        return Graphics("braille", where + "no Kitty-graphics terminal in the environment")
    try:
        import PIL  # noqa: F401
        _preset(True, cell)
        from textual_image.widget import TGPImage
    except Exception as exc:  # noqa: BLE001
        return Graphics("braille", f"graphics libraries unavailable ({type(exc).__name__})")
    return Graphics("kitty", kitty_reason, TGPImage, cell)


# ---- geometry ----------------------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def world() -> list[tuple[str, list[list[list[tuple[float, float]]]]]]:
    raw = rank._load("world110m.json")
    return [(str(cid), [[[(float(x), float(y)) for x, y in ring] for ring in poly] for poly in polys]) for cid, polys in raw]


@dataclass
class View:
    kind: str = "tactical"  # tactical | flat
    lon: float = 10.0
    lat: float = 20.0


def _project(view: View, w: float, h: float):
    """Returns project(lon, lat) -> (x, y, front) in a w x h box (dot or pixel space)."""
    if view.kind == "flat":
        sx, sy = w / 360.0, h / 180.0

        def flat(lon: float, lat: float) -> tuple[float, float, bool]:
            d = (lon - view.lon + 180.0) % 360.0 - 180.0
            return (d + 180.0) * sx, (90.0 - lat) * sy, True
        return flat
    r = min(w / 2.0, h / 2.0) * 0.96
    cx, cy = w / 2.0, h / 2.0
    lam0, phi0 = math.radians(view.lon), math.radians(view.lat)
    sp0, cp0 = math.sin(phi0), math.cos(phi0)

    def ortho(lon: float, lat: float) -> tuple[float, float, bool]:
        lam, phi = math.radians(lon), math.radians(lat)
        cosc = sp0 * math.sin(phi) + cp0 * math.cos(phi) * math.cos(lam - lam0)
        x = math.cos(phi) * math.sin(lam - lam0)
        y = cp0 * math.sin(phi) - sp0 * math.cos(phi) * math.cos(lam - lam0)
        if cosc < 0:  # far side: pull to the limb
            n = math.hypot(x, y) or 1.0
            x, y = x / n, y / n
        return cx + x * r, cy - y * r, cosc >= 0
    return ortho


@lru_cache(maxsize=1)
def _world_trig() -> list[tuple[str, list[tuple[list[float], list[float], list[float]]]]]:
    """0.2.2: per vertex radians(lon), sin(radians(lat)) and cos(radians(lat)), computed once (the same values the
    orthographic projection computes per frame), so a globe frame costs two trig calls per vertex instead of seven."""
    out = []
    for cid, polys in world():
        rings = []
        for poly in polys:
            for ring in poly:
                phis = [math.radians(lat) for _, lat in ring]
                rings.append(([math.radians(lon) for lon, _ in ring], [math.sin(p) for p in phis], [math.cos(p) for p in phis]))
        out.append((cid, rings))
    return out


def _rings_ortho(view: View, w: float, h: float) -> list[tuple[str, list[tuple[float, float]]]]:
    """``_rings`` for the tactical globe: the exact arithmetic of ``_project``'s ortho (bit-identical points), inlined
    over the cached per-vertex trig (0.2.2, the smoother Live globe within its CPU budget)."""
    r = min(w / 2.0, h / 2.0) * 0.96
    cx, cy = w / 2.0, h / 2.0
    lam0, phi0 = math.radians(view.lon), math.radians(view.lat)
    sp0, cp0 = math.sin(phi0), math.cos(phi0)
    cos, sin, hypot = math.cos, math.sin, math.hypot
    out: list[tuple[str, list[tuple[float, float]]]] = []
    for cid, rings in _world_trig():
        for lams, sphis, cphis in rings:
            xy: list[tuple[float, float]] = []
            front_any = False
            for lam, sphi, cphi in zip(lams, sphis, cphis, strict=True):
                cd = cos(lam - lam0)
                cosc = sp0 * sphi + cp0 * cphi * cd
                x = cphi * sin(lam - lam0)
                y = cp0 * sphi - sp0 * cphi * cd
                if cosc < 0:  # far side: pull to the limb
                    n = hypot(x, y) or 1.0
                    x, y = x / n, y / n
                else:
                    front_any = True
                xy.append((cx + x * r, cy - y * r))
            if front_any:
                out.append((cid, xy))
    return out


def _rings(view: View, w: float, h: float) -> list[tuple[str, list[tuple[float, float]]]]:
    """Projected outer and inner rings per country; rings wholly on the far side are dropped. Flat rings that cross
    the seam are unwrapped and drawn shifted by the map width too."""
    if view.kind != "flat":
        return _rings_ortho(view, w, h)
    proj = _project(view, w, h)
    out: list[tuple[str, list[tuple[float, float]]]] = []
    for cid, polys in world():
        for poly in polys:
            for ring in poly:
                pts = [proj(lon, lat) for lon, lat in ring]
                if not any(front for _, _, front in pts):
                    continue
                xy = [(x, y) for x, y, _ in pts]
                if view.kind == "flat":
                    fixed = [xy[0]]
                    for x, y in xy[1:]:
                        px = fixed[-1][0]
                        while x - px > w / 2:
                            x -= w
                        while px - x > w / 2:
                            x += w
                        fixed.append((x, y))
                    xs = [x for x, _ in fixed]
                    out.append((cid, fixed))
                    if min(xs) < 0:
                        out.append((cid, [(x + w, y) for x, y in fixed]))
                    if max(xs) > w:
                        out.append((cid, [(x - w, y) for x, y in fixed]))
                else:
                    out.append((cid, xy))
    return out


@lru_cache(maxsize=8)
def raster(view_key: tuple[str, float, float], w: int, h: int) -> tuple[tuple[str, ...], ...]:
    """Country id per dot ("" = sea or space) for a w x h dot grid, by even-odd scanline fill of every ring."""
    view = View(*view_key)
    grid = [[""] * w for _ in range(h)]
    for cid, ring in _rings(view, w, h):
        n = len(ring)
        crossings: dict[int, list[float]] = {}
        for i in range(n - 1):
            (x1, y1), (x2, y2) = ring[i], ring[i + 1]
            if y1 == y2:
                continue
            lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
            for row in range(max(0, math.ceil(lo - 0.5)), min(h - 1, math.floor(hi - 0.5)) + 1):
                yc = row + 0.5
                if lo <= yc < hi:
                    crossings.setdefault(row, []).append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
        for row, xs in crossings.items():
            xs.sort()
            for a, b in zip(xs[0::2], xs[1::2], strict=False):
                for col in range(max(0, math.ceil(a - 0.5)), min(w - 1, math.floor(b - 0.5)) + 1):
                    grid[row][col] = cid if grid[row][col] != cid else ""  # even-odd for holes
    return tuple(tuple(r) for r in grid)


# ---- scene -------------------------------------------------------------------------------------------------------


@dataclass
class Scene:
    counts: dict[str, int] = field(default_factory=dict)
    points: list[tuple[float, float, bool]] = field(default_factory=list)  # lat, lon, breaking
    arcs: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    pins: list[tuple[float, float]] = field(default_factory=list)
    selected: str | None = None
    now_ms: float = 0.0


def scene_from(mdata: rank.MapData, now_ms: float, selected: str | None = None) -> Scene:
    points = [(loc["lat"], loc["lng"], loc["freshest"] is not None and loc["freshest"] < 120) for loc in mdata.locations]
    arcs = [((a["from"].lat, a["from"].lon), (a["to"].lat, a["to"].lon)) for a in mdata.arcs]
    live = {u for u in mdata.published_at}
    pins = [(a["lat"], a["lon"]) for a in mdata.displayed if a["url"] not in live]
    return Scene(dict(mdata.counts), points, arcs, pins, selected, now_ms)


def subsolar(now_ms: float) -> tuple[float, float]:
    """Approximate sub-solar point (lat, lon) for the day/night layer."""
    d = now_ms / 86400000.0 + 2440587.5 - 2451545.0
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    lam = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.00000036 * d)
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam)))
    gmst = (280.46061837 + 360.98564736629 * d) % 360
    lon = (ra - gmst + 540) % 360 - 180
    return dec, lon


def _night(lat: float, lon: float, sun: tuple[float, float]) -> bool:
    p1, p2 = math.radians(lat), math.radians(sun[0])
    return (math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(math.radians(lon - sun[1]))) < 0


def _inverse(view: View, w: int, h: int, x: float, y: float) -> tuple[float, float] | None:
    if view.kind == "flat":
        return 90.0 - y * 180.0 / h, (x * 360.0 / w - 180.0 + view.lon + 540) % 360 - 180
    r = min(w / 2.0, h / 2.0) * 0.96
    px, py = (x - w / 2.0) / r, (h / 2.0 - y) / r
    rho = math.hypot(px, py)
    if rho > 1:
        return None
    c = math.asin(rho)
    phi0, lam0 = math.radians(view.lat), math.radians(view.lon)
    if rho == 0:
        return view.lat, view.lon
    lat = math.asin(math.cos(c) * math.sin(phi0) + py * math.sin(c) * math.cos(phi0) / rho)
    lon = lam0 + math.atan2(px * math.sin(c), rho * math.cos(phi0) * math.cos(c) - py * math.sin(phi0) * math.sin(c))
    return math.degrees(lat), (math.degrees(lon) + 540) % 360 - 180


def _line(a: tuple[float, float], b: tuple[float, float], steps: int) -> list[tuple[float, float]]:
    """Great-circle points between two (lat, lon)."""
    (la1, lo1), (la2, lo2) = (tuple(map(math.radians, a)), tuple(map(math.radians, b)))
    v1 = (math.cos(la1) * math.cos(lo1), math.cos(la1) * math.sin(lo1), math.sin(la1))
    v2 = (math.cos(la2) * math.cos(lo2), math.cos(la2) * math.sin(lo2), math.sin(la2))
    out = []
    for i in range(steps + 1):
        t = i / steps
        v = [v1[k] * (1 - t) + v2[k] * t for k in range(3)]
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        x, y, z = (c / n for c in v)
        out.append((math.degrees(math.asin(z)), math.degrees(math.atan2(y, x))))
    return out


def heat_colour(p: Palette, level: int) -> str:
    return mix(p.muted, p.accent, (0.2, 0.4, 0.6, 0.8, 1.0)[max(1, min(5, level)) - 1]) if level else p.muted


# ---- Braille -----------------------------------------------------------------------------------------------------

_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # dot (row, col) -> Braille bit


def render_braille(scene: Scene, view: View, layers: dict[str, bool], cols: int, rows: int, p: Palette) -> Text:
    """A cols x rows Braille map: land as a light dot texture, countries with news in heat colours, story points,
    breaking rings, link arcs, pins, exchanges, the night side dimmed and an optional graticule."""
    w, h = cols * 2, rows * 4
    grid = raster((view.kind, round(view.lon, 1), view.lat), w, h)
    proj = _project(view, w, h)
    sun = subsolar(scene.now_ms) if layers.get("terminator") else None
    on = [[0] * cols for _ in range(rows)]
    role = [[0] * cols for _ in range(rows)]  # priority: 0 none, 1 grid, 2 land, 3 night land, 4 heat, 5 arc, 6 pin, 7 ex,
    # 8 point, 9 ring, 10 selected
    heat_lvl = [[0] * cols for _ in range(rows)]

    def put(x: float, y: float, r: int, lvl: int = 0) -> None:
        xi, yi = int(x), int(y)
        if 0 <= xi < w and 0 <= yi < h:
            c, rr = xi // 2, yi // 4
            on[rr][c] |= _BITS[yi % 4][xi % 2]
            if r > role[rr][c]:
                role[rr][c] = r
            if lvl > heat_lvl[rr][c]:
                heat_lvl[rr][c] = lvl

    for y in range(h):
        line = grid[y]
        for x in range(w):
            cid = line[x]
            if not cid:
                continue
            n = scene.counts.get(cid, 0)
            if cid == scene.selected:
                put(x, y, 10)
            elif n and layers.get("heat"):
                put(x, y, 4, rank.heat_level(n))
            elif (x + y) % 2 == 0:
                night = False
                if sun is not None:
                    ll = _inverse(view, w, h, (x // 4) * 4 + 2.0, (y // 4) * 4 + 2.0)
                    night = ll is not None and _night(ll[0], ll[1], sun)
                put(x, y, 3 if night else 2)
    if view.kind == "tactical":
        r = min(w / 2.0, h / 2.0) * 0.96
        for i in range(0, 360, 2):
            a = math.radians(i)
            put(w / 2 + r * math.cos(a), h / 2 + r * math.sin(a), 1)
    if layers.get("graticule"):
        for lon_i in range(-180, 180, 30):
            for lat_i in range(-80, 81, 2):
                x, y, front = proj(lon_i, lat_i)
                if front:
                    put(x, y, 1)
        for lat_i in range(-60, 61, 30):
            for lon_j in range(-180, 180, 2):
                x, y, front = proj(lon_j, lat_i)
                if front:
                    put(x, y, 1)
    if layers.get("arcs"):
        for src, dst in scene.arcs:
            for lat, lon in _line(src, dst, 40):
                x, y, front = proj(lon, lat)
                if front:
                    put(x, y, 5)
    if layers.get("pins"):
        for lat, lon in scene.pins:
            x, y, front = proj(lon, lat)
            if front:
                put(x, y, 6)
    if layers.get("exchanges"):
        for lat, lon in EXCHANGES:
            x, y, front = proj(lon, lat)
            if front:
                put(x, y, 7)
    for lat, lon, breaking in scene.points:
        x, y, front = proj(lon, lat)
        if not front:
            continue
        if layers.get("points"):
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                put(x + dx, y + dy, 8)
        if breaking and layers.get("rings"):
            for i in range(0, 360, 45):
                a = math.radians(i)
                put(x + 3 * math.cos(a), y + 3 * math.sin(a), 9)
    styles = {1: p.panel if p.panel != p.background else p.muted, 2: mix(p.muted, p.background, 0.25),
              3: mix(p.muted, p.background, 0.6), 5: p.secondary, 6: p.success, 7: p.foreground, 8: p.accent,
              9: p.warning, 10: p.foreground}
    text = Text(no_wrap=True, overflow="crop")
    for rr in range(rows):
        run_style = None
        run: list[str] = []
        for c in range(cols):
            bits = on[rr][c]
            ch = chr(0x2800 + bits) if bits else " "
            r = role[rr][c]
            st = heat_colour(p, heat_lvl[rr][c]) if r == 4 else styles.get(r) if bits else None
            if st != run_style and run:
                text.append("".join(run), style=run_style or "")
                run = []
            run_style = st
            run.append(ch)
        if run:
            text.append("".join(run), style=run_style or "")
        if rr < rows - 1:
            text.append("\n")
    return text


# ---- Kitty image (Pillow) ----------------------------------------------------------------------------------------


def render_image(scene: Scene, view: View, layers: dict[str, bool], w: int, h: int, p: Palette) -> Any:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (max(8, w), max(8, h)), p.background)
    d = ImageDraw.Draw(im)
    proj = _project(view, w, h)
    if view.kind == "tactical":
        r = min(w / 2.0, h / 2.0) * 0.96
        d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=p.surface, outline=mix(p.background, p.primary, 0.4))
    land = mix(p.muted, p.background, 0.55)
    edge = mix(p.background, p.primary, 0.4)
    for cid, ring in _rings(view, w, h):
        n = scene.counts.get(cid, 0)
        fill = p.foreground if cid == scene.selected else heat_colour(p, rank.heat_level(n)) if n and layers.get("heat") else land
        if len(ring) >= 3:
            d.polygon(ring, fill=fill, outline=edge)
    if layers.get("terminator"):
        sun = subsolar(scene.now_ms)
        sw, sh = max(2, w // 8), max(2, h // 8)
        small = Image.new("L", (sw, sh), 0)
        for y in range(sh):
            for x in range(sw):
                ll = _inverse(view, w, h, (x + 0.5) * w / sw, (y + 0.5) * h / sh)
                if ll is not None and _night(ll[0], ll[1], sun):
                    small.putpixel((x, y), 90)
        mask = small.resize(im.size, Image.Resampling.BILINEAR)
        im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, mask)
        d = ImageDraw.Draw(im)
    if layers.get("graticule"):
        for lon_i in range(-180, 180, 30):
            pts = [proj(lon_i, la) for la in range(-80, 81, 2)]
            for a, b in zip(pts, pts[1:], strict=False):
                if a[2] and b[2] and abs(a[0] - b[0]) < w / 2:
                    d.line((a[0], a[1], b[0], b[1]), fill=p.panel)
        for lat_i in range(-60, 61, 30):
            pts = [proj(lo, lat_i) for lo in range(-180, 181, 2)]
            for a, b in zip(pts, pts[1:], strict=False):
                if a[2] and b[2] and abs(a[0] - b[0]) < w / 2:
                    d.line((a[0], a[1], b[0], b[1]), fill=p.panel)
    unit = max(2, min(w, h) // 120)
    if layers.get("arcs"):
        for a, b in scene.arcs:
            pts = [proj(lon, lat) for lat, lon in _line(a, b, 48)]
            for s, t in zip(pts, pts[1:], strict=False):
                if s[2] and t[2] and abs(s[0] - t[0]) < w / 2:
                    d.line((s[0], s[1], t[0], t[1]), fill=p.secondary, width=max(1, unit // 2))
    for group, colour, on_ in ((scene.pins, p.success, layers.get("pins")),
                               ([(a, b) for a, b in EXCHANGES], p.foreground, layers.get("exchanges"))):
        if on_:
            for lat, lon in group:
                x, y, front = proj(lon, lat)
                if front:
                    d.rectangle((x - unit, y - unit, x + unit, y + unit), fill=colour)
    for lat, lon, breaking in scene.points:
        x, y, front = proj(lon, lat)
        if not front:
            continue
        if layers.get("points"):
            d.ellipse((x - 2 * unit, y - 2 * unit, x + 2 * unit, y + 2 * unit), fill=p.accent)
        if breaking and layers.get("rings"):
            d.ellipse((x - 5 * unit, y - 5 * unit, x + 5 * unit, y + 5 * unit), outline=p.warning, width=max(1, unit // 2))
    return im


# ---- text table (non-UTF-8 output) -------------------------------------------------------------------------------


def render_table(mdata: rank.MapData, rows: int, cols: int, p: Palette) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append("COUNTRY".ljust(max(8, cols - 16)) + "STORIES  HEAT\n", style=f"bold {p.accent}")
    for country, n in mdata.ranked[: max(1, rows - 1)]:
        level = rank.heat_level(n)
        text.append(country.name[: max(8, cols - 16)].ljust(max(8, cols - 16)))
        text.append(f"{n:>7}  ")
        text.append("#" * level + "." * (5 - level) + "\n", style=heat_colour(p, level))
    if not mdata.ranked:
        text.append("No places in the stories yet.", style=p.muted)
    return text
