"""Theme registry, dynamic Rich palette synchronization, and persistence for SKTUI.

Bridges Textual 8.x CSS themes (`app.theme` / `textual.theme.Theme`) with Python-side
Rich `Text` and chart renderables so switching themes dynamically re-themes 100% of
the workstation — across dark and light modes, built-in themes, and signature presets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.theme import BUILTIN_THEMES, Theme

from sktui.config import CONFIG_FILE
from sktui.utils import read_json, write_private

DEFAULT_THEME = "sktui-obsidian"

# ── Curated Institutional Trading Themes ──────────────────────────────────────
SKTUI_THEMES: list[Theme] = [
    Theme(
        name="sktui-obsidian",
        primary="#00e5ff",
        secondary="#38bdf8",
        accent="#f59e0b",
        foreground="#e2e8f0",
        background="#060911",
        surface="#0b1120",
        panel="#132038",
        success="#10b981",
        warning="#f59e0b",
        error="#f43f5e",
        dark=True,
        variables={
            "border": "#00e5ff",
            "border-blurred": "#162032",
            "footer-background": "#080c17",
            "footer-key-foreground": "#00e5ff",
            "footer-key-background": "#0d1b2e",
        },
    ),
    Theme(
        name="sktui-bloomberg",
        primary="#ff9900",
        secondary="#00d7ff",
        accent="#ffd600",
        foreground="#f5f5f5",
        background="#050505",
        surface="#0f0f0f",
        panel="#1c1c1c",
        success="#00e676",
        warning="#ffab00",
        error="#ff3d00",
        dark=True,
        variables={
            "border": "#ff9900",
            "border-blurred": "#262626",
            "footer-background": "#0a0a0a",
            "footer-key-foreground": "#050505",
            "footer-key-background": "#ff9900",
        },
    ),
    Theme(
        name="sktui-emerald",
        primary="#10b981",
        secondary="#14b8a6",
        accent="#34d399",
        foreground="#ecfdf5",
        background="#050c0a",
        surface="#0a1612",
        panel="#122921",
        success="#22c55e",
        warning="#eab308",
        error="#fb7185",
        dark=True,
        variables={
            "border": "#10b981",
            "border-blurred": "#163027",
            "footer-background": "#07120e",
            "footer-key-foreground": "#10b981",
            "footer-key-background": "#0f2920",
        },
    ),
    Theme(
        name="sktui-midnight",
        primary="#a78bfa",
        secondary="#38bdf8",
        accent="#f472b6",
        foreground="#ede9fe",
        background="#090814",
        surface="#110f24",
        panel="#1c1938",
        success="#34d399",
        warning="#fbbf24",
        error="#fb7185",
        dark=True,
        variables={
            "border": "#a78bfa",
            "border-blurred": "#241f47",
            "footer-background": "#0d0b1c",
            "footer-key-foreground": "#a78bfa",
            "footer-key-background": "#1c1938",
        },
    ),
    Theme(
        name="sktui-daylight",
        primary="#0284c7",
        secondary="#0369a1",
        accent="#d97706",
        foreground="#0f172a",
        background="#f8fafc",
        surface="#ffffff",
        panel="#e2e8f0",
        success="#059669",
        warning="#d97706",
        error="#dc2626",
        dark=False,
        variables={
            "border": "#0284c7",
            "border-blurred": "#cbd5e1",
            "footer-background": "#e2e8f0",
            "footer-key-foreground": "#ffffff",
            "footer-key-background": "#0284c7",
        },
    ),
]

SKTUI_THEME_MAP: dict[str, Theme] = {t.name: t for t in SKTUI_THEMES}

THEME_DESCRIPTIONS: dict[str, str] = {
    "sktui-obsidian":   "Institutional Obsidian & Electric Cyan (Default)",
    "sktui-bloomberg":  "Classic Bloomberg Terminal Amber on Pitch Black",
    "sktui-emerald":    "Quant Matrix Slate & Emerald Execution Desk",
    "sktui-midnight":   "Deep Indigo & Violet Multi-Asset Research",
    "sktui-daylight":   "High-Contrast Institutional Alabaster Light Mode",
    "tokyo-night":      "Tokyo Night Storm — Neon Blue & Indigo",
    "catppuccin-mocha": "Catppuccin Mocha — Warm Pastel Dark",
    "nord":             "Nord — Arctic Bluish Polar Night",
    "gruvbox":          "Gruvbox — Retro Warm Groove Dark",
    "dracula":          "Dracula — High-Contrast Purple Vampire Dark",
    "monokai":          "Monokai — Classic Code Editor Charcoal",
    "rose-pine":        "Rosé Pine — Soho Natural Pine & Gold",
    "rose-pine-moon":   "Rosé Pine Moon — Deep Twilight Variant",
    "rose-pine-dawn":   "Rosé Pine Dawn — Warm Cream Light Mode",
    "flexoki":          "Flexoki — Inky Warm Paper Black",
    "solarized-dark":   "Solarized Dark — Precision Teal Slate",
    "solarized-light":  "Solarized Light — Warm Parchment Light Mode",
    "catppuccin-latte": "Catppuccin Latte — Crisp Espresso Light Mode",
    "atom-one-dark":    "Atom One Dark — Balanced Slate Blue",
    "atom-one-light":   "Atom One Light — Clean Minimal Daylight",
    "textual-dark":     "Textual Default Dark",
    "textual-light":    "Textual Default Light",
}

# Mapping for Textual's `ansi-*` theme tokens so Rich `Text` never receives invalid colors.
_ANSI_HEX_MAP: dict[str, str] = {
    "ansi_black":          "#18181b",
    "ansi_red":            "#ef4444",
    "ansi_green":          "#22c55e",
    "ansi_yellow":         "#eab308",
    "ansi_blue":           "#3b82f6",
    "ansi_magenta":        "#a855f7",
    "ansi_cyan":           "#06b6d4",
    "ansi_white":          "#f4f4f5",
    "ansi_bright_black":   "#52525b",
    "ansi_bright_red":     "#f87171",
    "ansi_bright_green":   "#4ade80",
    "ansi_bright_yellow":  "#facc15",
    "ansi_bright_blue":    "#60a5fa",
    "ansi_bright_magenta": "#c084fc",
    "ansi_bright_cyan":    "#22d3ee",
    "ansi_bright_white":   "#ffffff",
}


# ── Hex Color Math ────────────────────────────────────────────────────────────

def _sanitize_hex(value: str | None, fallback: str) -> str:
    """Convert a CSS color token to a clean `#rrggbb` string safe for Rich `Text`."""
    if not value:
        return fallback
    raw = str(value).strip().lower()
    # Strip trailing alpha percentages like `'ansi_blue 50%'` or `'#00e5ff 20%'`
    if " " in raw:
        first = raw.split()[0]
        if first in ("auto", "transparent", "ansi_default"):
            return fallback
        raw = first
    if raw in _ANSI_HEX_MAP:
        return _ANSI_HEX_MAP[raw]
    if raw in ("auto", "transparent", "ansi_default", "none", "initial", "inherit"):
        return fallback
    if raw.startswith("#"):
        hex_part = raw[1:]
        if len(hex_part) == 3 and all(c in "0123456789abcdef" for c in hex_part):
            return "#" + "".join(c * 2 for c in hex_part)
        if len(hex_part) in (6, 8) and all(c in "0123456789abcdef" for c in hex_part):
            return "#" + hex_part[:6]
    return fallback


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = _sanitize_hex(hex_color, "#808080")[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _blend_hex(c1: str, c2: str, alpha: float) -> str:
    """Blend `alpha` of `c1` with `(1 - alpha)` of `c2`."""
    a = max(0.0, min(1.0, alpha))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(round(r1 * a + r2 * (1.0 - a))),
        int(round(g1 * a + g2 * (1.0 - a))),
        int(round(b1 * a + b2 * (1.0 - a))),
    )


def _luminance(hex_color: str) -> float:
    """Compute WCAG relative luminance in [0.0, 1.0]."""
    r, g, b = _hex_to_rgb(hex_color)

    def _chan(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * _chan(r) + 0.7152 * _chan(g) + 0.0722 * _chan(b)


def _contrast_fg(bg_hex: str, dark_ink: str = "#060911", light_ink: str = "#ffffff") -> str:
    """Choose crisp dark or light foreground text for a solid badge background."""
    return dark_ink if _luminance(bg_hex) > 0.34 else light_ink


# ── Semantic Rich Palette ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ThemePalette:
    """Resolved `#rrggbb` semantic palette for Rich `Text` & terminal charts."""
    name: str
    dark: bool
    bg: str
    surface: str
    panel: str
    fg: str
    fg_strong: str
    muted: str
    subtle: str
    divider: str
    primary: str
    secondary: str
    accent: str
    bull: str
    bear: str
    warn: str
    teal: str
    on_primary: str
    on_secondary: str
    on_bull: str
    on_bear: str
    on_warn: str
    primary_tint: str
    bull_grad: tuple[str, ...]
    bear_grad: tuple[str, ...]

    def badge_color(self, raw_color: str) -> str:
        """Map standalone status colors (from QuoteStore/FeedHealth) onto theme-safe colors."""
        low = (raw_color or "").strip().lower()
        if low in ("#00ff87", "#10b981", "#22c55e", "#00e676"):
            return self.bull
        if low in ("#f59e0b", "#ffaa00", "#eab308", "#ffab00"):
            return self.warn
        if low in ("#ff4757", "#ff5f5f", "#ef4444", "#f43f5e", "#dc2626"):
            return self.bear
        if low in ("#888888", "#64748b", "#475569"):
            return self.subtle
        return _sanitize_hex(raw_color, self.primary)


def _build_palette(
    name: str,
    dark: bool,
    bg: str,
    surface: str,
    panel: str,
    fg: str,
    primary: str,
    secondary: str,
    accent: str,
    bull: str,
    bear: str,
    warn: str,
) -> ThemePalette:
    default_bg = "#060911" if dark else "#f8fafc"
    default_surf = "#0b1120" if dark else "#ffffff"
    default_panel = "#132038" if dark else "#e2e8f0"
    default_fg = "#e2e8f0" if dark else "#0f172a"

    c_bg = _sanitize_hex(bg, default_bg)
    c_surf = _sanitize_hex(surface, _blend_hex(default_fg, c_bg, 0.06))
    c_panel = _sanitize_hex(panel, _blend_hex(default_fg, c_bg, 0.12))
    c_fg = _sanitize_hex(fg, default_fg)
    c_fg_strong = "#ffffff" if dark else "#090d16"

    c_prim = _sanitize_hex(primary, "#00e5ff" if dark else "#0284c7")
    c_sec = _sanitize_hex(secondary, _blend_hex(c_prim, c_fg, 0.7))
    c_acc = _sanitize_hex(accent, "#f59e0b" if dark else "#d97706")
    c_bull = _sanitize_hex(bull, "#10b981" if dark else "#059669")
    c_bear = _sanitize_hex(bear, "#f43f5e" if dark else "#dc2626")
    c_warn = _sanitize_hex(warn, "#f59e0b" if dark else "#d97706")
    c_teal = "#14b8a6" if dark else "#0d9488"

    c_muted = _blend_hex(c_fg, c_bg, 0.68)
    c_subtle = _blend_hex(c_fg, c_bg, 0.45)
    c_divider = _blend_hex(c_fg, c_bg, 0.25)
    c_prim_tint = _blend_hex(c_prim, c_surf, 0.22)

    bull_end = _blend_hex(c_bull, c_bg, 0.62)
    bear_end = _blend_hex(c_bear, c_bg, 0.62)
    bull_grad = tuple(_blend_hex(c_bull, bull_end, 1.0 - i / 5.0) for i in range(6))
    bear_grad = tuple(_blend_hex(c_bear, bear_end, 1.0 - i / 4.0) for i in range(5))

    return ThemePalette(
        name=name,
        dark=dark,
        bg=c_bg,
        surface=c_surf,
        panel=c_panel,
        fg=c_fg,
        fg_strong=c_fg_strong,
        muted=c_muted,
        subtle=c_subtle,
        divider=c_divider,
        primary=c_prim,
        secondary=c_sec,
        accent=c_acc,
        bull=c_bull,
        bear=c_bear,
        warn=c_warn,
        teal=c_teal,
        on_primary=_contrast_fg(c_prim),
        on_secondary=_contrast_fg(c_sec),
        on_bull=_contrast_fg(c_bull),
        on_bear=_contrast_fg(c_bear),
        on_warn=_contrast_fg(c_warn),
        primary_tint=c_prim_tint,
        bull_grad=bull_grad,
        bear_grad=bear_grad,
    )


def palette_from_theme(theme: Theme, css_vars: dict[str, str] | None = None) -> ThemePalette:
    """Construct a `ThemePalette` from a Textual `Theme` and optional resolved CSS vars."""
    v = css_vars or {}
    dark = bool(theme.dark)
    return _build_palette(
        name=theme.name,
        dark=dark,
        bg=theme.background or v.get("background") or "",
        surface=theme.surface or v.get("surface") or "",
        panel=theme.panel or v.get("panel") or "",
        fg=theme.foreground or v.get("foreground") or "",
        primary=theme.primary or v.get("primary") or "",
        secondary=theme.secondary or v.get("secondary") or theme.primary or "",
        accent=theme.accent or v.get("accent") or theme.warning or theme.primary or "",
        bull=theme.success or v.get("success") or "",
        bear=theme.error or v.get("error") or "",
        warn=theme.warning or v.get("warning") or "",
    )


def palette_for_theme_name(
    theme_name: str,
    available_themes: dict[str, Theme] | None = None,
) -> ThemePalette:
    """Resolve a `ThemePalette` by name across SKTUI custom themes and Textual built-ins."""
    lookup: dict[str, Theme] = {}
    lookup.update(BUILTIN_THEMES)
    lookup.update(SKTUI_THEME_MAP)
    if available_themes:
        lookup.update(available_themes)
    th = lookup.get(theme_name) or SKTUI_THEME_MAP[DEFAULT_THEME]
    return palette_from_theme(th)


# Global active singleton updated whenever `SKApp.watch_theme` runs.
_ACTIVE_PALETTE: ThemePalette = palette_from_theme(SKTUI_THEME_MAP[DEFAULT_THEME])


def current_palette(app: Any = None) -> ThemePalette:
    """Return the active `ThemePalette` (optionally syncing from *app* if provided)."""
    if app is not None:
        return sync_palette_from_app(app)
    return _ACTIVE_PALETTE


def sync_palette_from_app(app: Any) -> ThemePalette:
    """Synchronize `_ACTIVE_PALETTE` from a live Textual `App` instance."""
    global _ACTIVE_PALETTE
    try:
        th = getattr(app, "current_theme", None)
        css_vars = app.get_css_variables() if hasattr(app, "get_css_variables") else {}
        if th is not None:
            _ACTIVE_PALETTE = palette_from_theme(th, css_vars)
    except Exception:
        pass
    return _ACTIVE_PALETTE


# ── Theme Persistence in config.json ──────────────────────────────────────────

def load_configured_theme(config_file: Path = CONFIG_FILE) -> str:
    """Read saved theme name from env (`SKTUI_THEME`) or `config.json`."""
    env_theme = os.environ.get("SKTUI_THEME", "").strip()
    if env_theme:
        return env_theme
    cfg = read_json(config_file, {})
    if isinstance(cfg, dict):
        saved = str(cfg.get("theme", "")).strip()
        if saved:
            return saved
    return DEFAULT_THEME


def save_configured_theme(theme_name: str, config_file: Path = CONFIG_FILE) -> None:
    """Persist selected theme into `config.json` without clobbering credentials/profiles."""
    if not theme_name:
        return
    try:
        existing = read_json(config_file, {})
        if not isinstance(existing, dict):
            existing = {}
        if existing.get("theme") == theme_name:
            return
        existing["theme"] = theme_name
        write_private(config_file, existing)
    except Exception:
        pass
