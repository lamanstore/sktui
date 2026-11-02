"""Login screen view for SKTUI — Institutional Terminal Authentication Gateway."""
from __future__ import annotations

import os
import time
import webbrowser
from datetime import date
from typing import Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, Rule, Select, Static,
)

from sktui import api
from sktui.config import CONFIG_FILE, SESSION_FILE
from sktui.themes import current_palette
from sktui.utils import get_public_ip, read_json, write_private

LOGIN_LOGO = """\
 ╭──────────────────────────────────────────────────────────╮
 │    ███████╗██╗  ██╗████████╗██╗   ██╗██╗                 │
 │    ██╔════╝██║ ██╔╝╚══██╔══╝██║   ██║██║   INSTITUTIONAL │
 │    ███████╗█████╔╝    ██║   ██║   ██║██║   TRADING       │
 │    ╚════██║██╔═██╗    ██║   ██║   ██║██║   WORKSTATION   │
 │    ███████║██║  ██╗   ██║   ╚██████╔╝██║                 │
 │    ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝   v2.4 · PRO    │
 ├──────────────────────────────────────────────────────────┤
 │       Mirae Asset Sharekhan · Low-Latency Execution      │
 ╰──────────────────────────────────────────────────────────╯"""


class LoginScreen(Screen):
    BINDINGS = [
        Binding("ctrl+o", "open_browser", "Browser Auth"),
        Binding("ctrl+s", "launch_paper", "Paper Sandbox"),
        Binding("ctrl+g", "toggle_cfg", "API Config"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._public_ip: str = ""
        self._last_msg: tuple[str, bool] | None = None
        self._last_url: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="login-container"):
            with Vertical(id="login"):
                yield Static(LOGIN_LOGO, id="login-logo")
                yield Static("  ⟳  Detecting network gateway & public IP…", id="ip-display", classes="ip-display-card")
                with Vertical(id="api-config-box"):
                    yield Label(
                        " ── 01 · BROKER API CREDENTIALS ───────────────────────────────────────",
                        classes="section-label",
                    )
                    yield Input(placeholder="Sharekhan API Key", id="api_key")
                    yield Input(
                        placeholder="Secret Key (32-character AES/HMAC key)",
                        password=True,
                        id="secret",
                    )
                    yield Input(
                        placeholder="Vendor Key (optional — partner desks only)",
                        id="vendor",
                    )
                    yield Select(
                        [
                            ("v1005  ·  AES-256 Base64-URL (Recommended)", "1005"),
                            ("Legacy ·  Standard Base64", ""),
                        ],
                        value="1005",
                        allow_blank=False,
                        id="ver",
                    )
                    yield Checkbox(
                        " 🔒 Persist encrypted credentials in local XDG config (0600)",
                        id="remember",
                        value=True,
                    )
                    yield Rule()
                yield Label(
                    " ── 02 · DAILY SESSION HANDSHAKE ──────────────────────────────────────",
                    classes="section-label",
                )
                yield Button(
                    "⬡  Step 1 · Launch Sharekhan OAuth Portal in Browser  [Ctrl+O]",
                    id="geturl",
                    classes="btn-step",
                )
                yield Static("", id="url", classes="url-display")
                yield Input(
                    placeholder="Step 2 · Paste request_token or full redirect URL and press Enter ↵",
                    id="reqtok",
                )
                yield Rule()
                with Horizontal(classes="row buttons-bar"):
                    yield Button("⚙  API Config", id="toggle_config", classes="btn-step")
                    yield Button("◈  Paper Sandbox", id="paper_demo", classes="btn-step")
                    yield Button(
                        "⬢  Authenticate & Launch",
                        id="go",
                        variant="primary",
                        classes="btn-connect",
                    )
                yield Static("", id="msg", classes="login-msg")
        yield Footer()

    def on_mount(self) -> None:
        cfg, env = read_json(CONFIG_FILE, {}), os.environ
        api_k = env.get("SK_API_KEY")    or cfg.get("api_key", "")
        sec   = env.get("SK_SECRET_KEY") or cfg.get("secret", "")
        self.query_one("#api_key",  Input).value  = api_k
        self.query_one("#secret",   Input).value  = sec
        self.query_one("#vendor",   Input).value  = (env.get("SK_VENDOR_KEY") or cfg.get("vendor", ""))
        self.query_one("#ver",      Select).value = env.get("SK_VERSION_ID", cfg.get("version", "1005"))
        self.query_one("#remember", Checkbox).value = bool(cfg) or True
        self._fetch_public_ip()
        box = self.query_one("#api-config-box")
        if api_k and sec:
            box.display = False
            self.query_one("#reqtok", Input).focus()
        else:
            box.display = True
            self.query_one("#api_key", Input).focus()

        s   = read_json(SESSION_FILE, {})
        exp = api.jwt_exp(s.get("access_token", "")) if s else None
        if s and ((exp and exp > time.time() + 120)
                  or (not exp and s.get("date") == str(date.today()))):
            self.msg("⚡ Resuming active daily session…")
            self.finish(s)

    def post(self, fn: Any, *a: Any) -> None:
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    @work(thread=True)
    def _fetch_public_ip(self) -> None:
        ip = get_public_ip()
        self.post(self._show_public_ip, ip)

    def _show_public_ip(self, ip: str) -> None:
        self._public_ip = ip
        try:
            p = current_palette()
            t = Text()
            mode_str = "PAPER" if getattr(self.app, "paper", False) else "LIVE"
            mode_clr = p.warn if mode_str == "PAPER" else p.bull
            mode_fg = p.on_warn if mode_str == "PAPER" else p.on_bull
            t.append(f" ◈ {mode_str} ", style=f"bold {mode_fg} on {mode_clr}")
            t.append("  🌐 Gateway IP: ", style=p.muted)
            t.append(f"{ip}  ", style=f"bold {p.primary}")
            t.append("· Whitelist in Sharekhan Portal", style=p.subtle)
            self.query_one("#ip-display", Static).update(t)
        except Exception:
            pass

    def on_theme_changed(self) -> None:
        """Re-render Rich Text widgets on LoginScreen when theme changes."""
        if self._public_ip:
            self._show_public_ip(self._public_ip)
        if self._last_msg is not None:
            self.msg(*self._last_msg)
        if self._last_url:
            try:
                self.query_one("#url", Static).update(
                    Text(f"  🔗 {self._last_url}", style=current_palette().primary)
                )
            except Exception:
                pass

    def action_toggle_cfg(self) -> None:
        self._toggle_config()

    def action_open_browser(self) -> None:
        self._geturl()

    def action_launch_paper(self) -> None:
        self._launch_paper_sandbox()

    @on(Button.Pressed, "#toggle_config")
    def _toggle_config(self) -> None:
        box = self.query_one("#api-config-box")
        box.display = not box.display

    @on(Button.Pressed, "#paper_demo")
    def _launch_paper_sandbox(self) -> None:
        self.app.paper = True
        sess = {
            "date": str(date.today()),
            "api_key": "PAPER_SANDBOX_KEY",
            "vendor": "",
            "access_token": "PAPER_SANDBOX_TOKEN",
            "customer_id": "PAPER-01",
            "login_id": "PAPER_TRADER",
            "exchanges": ["NC", "BC", "NF", "RN", "MX"],
            "full_name": "PAPER SANDBOX DESK",
        }
        self.msg("◈ Launching Paper Simulation Workstation…")
        self.finish(sess)

    def msg(self, text: str, error: bool = False) -> None:
        self._last_msg = (text, error)
        p = current_palette()
        t = Text()
        if error:
            t.append(" ✗ ERROR ", style=f"bold {p.on_bear} on {p.bear}")
            t.append(f"  {text}", style=f"bold {p.bear}")
        else:
            t.append(" ✓ READY ", style=f"bold {p.on_bull} on {p.bull}")
            t.append(f"  {text}", style=f"bold {p.bull}")
        try:
            self.query_one("#msg", Static).update(t)
        except Exception:
            pass

    def fields(self) -> dict:
        g = lambda i: self.query_one(f"#{i}", Input).value.strip()
        return {
            "api_key": g("api_key"), "secret": g("secret"),
            "vendor":  g("vendor"),  "reqtok": g("reqtok"),
            "version": str(self.query_one("#ver", Select).value or ""),
        }

    @on(Button.Pressed, "#geturl")
    def _geturl(self) -> None:
        f = self.fields()
        if not f["api_key"]:
            return self.msg("API key is required — open API Config to set it", True)
        url = api.login_url(f["api_key"], f["vendor"], f["version"])
        self._last_url = url
        self.query_one("#url", Static).update(Text(f"  🔗 {url}", style=current_palette().primary))
        try:
            webbrowser.open(url)
        except Exception:
            pass
        self.msg("Browser opened — authenticate, then paste the request token below.")

    @on(Input.Submitted, "#reqtok")
    def _reqtok_enter(self) -> None:
        self._go()

    @on(Button.Pressed, "#go")
    def _go(self) -> None:
        f = self.fields()
        if not all([f["api_key"], f["secret"], f["reqtok"]]):
            return self.msg("API key, secret, and request token are all required (or click Paper Sandbox)", True)
        self.msg("⟳  Performing cryptographic session handshake…")
        self.authenticate(f)

    @work(thread=True)
    def authenticate(self, f: dict) -> None:
        try:
            d = api.fetch_access_token(
                f["api_key"], f["secret"], f["reqtok"], f["vendor"], f["version"])
        except Exception as e:
            self.app.call_from_thread(self.msg, f"Authentication failed: {e}", True)
            return
        sess = {
            "date":         str(date.today()),
            "api_key":      f["api_key"],
            "vendor":       f["vendor"],
            "access_token": d["token"],
            "customer_id":  str(d.get("customerId", "")),
            "login_id":     str(d.get("loginId", "")),
            "exchanges":    d.get("exchanges", []),
            "full_name":    d.get("fullName", ""),
        }
        self.app.call_from_thread(self.after_auth, f, sess)

    def after_auth(self, f: dict, sess: dict) -> None:
        if self.query_one("#remember", Checkbox).value:
            existing = read_json(CONFIG_FILE, {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update({
                "api_key": f["api_key"], "secret": f["secret"],
                "vendor":  f["vendor"],  "version": f["version"],
            })
            write_private(CONFIG_FILE, existing)
        write_private(SESSION_FILE, sess)
        self.finish(sess)

    def finish(self, s: dict) -> None:
        from sktui.screens.main import MainScreen
        self.app.client = api.Client(
            s["api_key"], s["access_token"], s["customer_id"],
            s.get("login_id", ""), s.get("vendor", ""),
            s.get("exchanges", []), s.get("full_name", ""), self.app.paper,
        )
        self.app.switch_screen(MainScreen())
