"""Login screen view for SKTUI."""
from __future__ import annotations

import os
import time
import webbrowser
from datetime import date

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Checkbox, Input, Label, Rule, Select, Static,
)

from sktui import api
from sktui.config import C_AMBER, C_CYAN, C_GREEN, C_MUTED, C_RED, C_SUBTLE, CONFIG_FILE, SESSION_FILE
from sktui.utils import get_public_ip, read_json, write_private

LOGIN_LOGO = """\
 ╔══════════════════════════════════════╗
 ║   ███████╗██╗  ██╗████████╗██╗   ██╗ ║
 ║   ██╔════╝██║ ██╔╝╚══██╔══╝██║   ██║ ║
 ║   ███████╗█████╔╝    ██║   ██║   ██║ ║
 ║   ╚════██║██╔═██╗    ██║   ██║   ██║ ║
 ║   ███████║██║  ██╗   ██║   ╚██████╔╝ ║
 ║   ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝  ║
 ╠══════════════════════════════════════╣
 ║    Mirae Asset Sharekhan Terminal    ║
 ╚══════════════════════════════════════╝"""


class LoginScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="login-container"):
            with Vertical(id="login"):
                yield Static(LOGIN_LOGO, id="login-logo")
                yield Rule()
                with Vertical(id="api-config-box"):
                    yield Label(
                        "\u2500\u2500\u2500 API CREDENTIALS \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                        classes="section-label")
                    yield Input(placeholder="API Key", id="api_key")
                    yield Input(placeholder="Secret Key  (32 chars)",
                                password=True, id="secret")
                    yield Input(placeholder="Vendor Key  (partners only, leave blank otherwise)",
                                id="vendor")
                    yield Select(
                        [("v1005  (Base64-URL \u2014 recommended)", "1005"),
                         ("No version  (Base64)", "")],
                        value="1005", allow_blank=False, id="ver",
                    )
                    yield Static("  ⟳  Fetching Public IP…", id="ip-display", classes="ip-display-card")
                    yield Checkbox(" \U0001f512  Save API credentials to config file",
                                   id="remember", value=True)
                    yield Rule()
                yield Label(
                    "\u2500\u2500\u2500 DAILY SESSION AUTH \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                    classes="section-label")
                yield Button(
                    "\u2b21  Step 1 \u00b7 Open Login Page in Browser",
                    id="geturl", classes="btn-step")
                yield Static("", id="url", classes="url-display")
                yield Input(
                    placeholder="Step 2 \u00b7 Paste request token or full redirect URL",
                    id="reqtok")
                yield Rule()
                with Horizontal(classes="row buttons-bar"):
                    yield Button("\u2699  API Config", id="toggle_config", classes="btn-step")
                    yield Button("\u2b22  Connect to Sharekhan", id="go", variant="primary", classes="btn-connect")
                yield Static("", id="msg", classes="login-msg")

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
            self.msg("\u26a1 Resuming saved session\u2026")
            self.finish(s)

    @work(thread=True)
    def _fetch_public_ip(self) -> None:
        ip = get_public_ip()
        self.post(self._show_public_ip, ip)

    def _show_public_ip(self, ip: str) -> None:
        try:
            t = Text()
            t.append("  🌐 Machine Public IP: ", style=C_MUTED)
            t.append(f"{ip}  ", style=f"bold {C_CYAN}")
            t.append("(Whitelist this IP in Sharekhan Portal)", style=C_SUBTLE)
            self.query_one("#ip-display", Static).update(t)
        except Exception:
            pass

    @on(Button.Pressed, "#toggle_config")
    def _toggle_config(self) -> None:
        box = self.query_one("#api-config-box")
        box.display = not box.display

    def msg(self, text: str, error: bool = False) -> None:
        style  = f"bold {C_RED}"   if error else f"bold {C_GREEN}"
        prefix = "\u2717 "         if error else "\u2713 "
        self.query_one("#msg", Static).update(Text(prefix + text, style=style))

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
            return self.msg("API key is required", True)
        url = api.login_url(f["api_key"], f["vendor"], f["version"])
        self.query_one("#url", Static).update(Text(url, style=C_GREEN))
        try:
            webbrowser.open(url)
        except Exception:
            pass
        self.msg("Browser opened \u2014 log in, then paste the request token below.")

    @on(Button.Pressed, "#go")
    def _go(self) -> None:
        f = self.fields()
        if not all([f["api_key"], f["secret"], f["reqtok"]]):
            return self.msg("API key, secret, and request token are all required", True)
        self.msg("\u27f3  Authenticating \u2014 please wait\u2026")
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
            write_private(CONFIG_FILE, {
                "api_key": f["api_key"], "secret": f["secret"],
                "vendor":  f["vendor"],  "version": f["version"],
            })
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
