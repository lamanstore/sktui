"""Textual CSS styles for SKTUI — Theme-Reactive Institutional Trading Terminal.

Uses Textual 8.x semantic theme variables (`$background`, `$surface`, `$panel`,
`$primary`, `$secondary`, `$accent`, `$foreground`, `$text-muted`, `$border`,
`$border-blurred`, `$success`, `$warning`, `$error`, etc.) so switching themes
via `Ctrl+P`, `Ctrl+T`, or `/theme` dynamically re-styles every surface, border,
table, input, button, and modal across both dark and light modes.
"""
from __future__ import annotations

CSS = """
/* ═══════════════════════════════════════════════════════════════════════════
   BASE / RESET
═══════════════════════════════════════════════════════════════════════════ */
Screen {
    background: $background;
    color: $foreground;
    layers: base overlay;
}

/* ═══════════════════════════════════════════════════════════════════════════
   HEADER & FOOTER
═══════════════════════════════════════════════════════════════════════════ */
Header {
    background: $surface;
    color: $primary;
    text-style: bold;
    border: none;
    height: 1;
}
Header > .header--title     { color: $primary; text-style: bold; }
Header > .header--sub-title { color: $text-muted; }

Footer {
    background: $footer-background;
    color: $footer-description-foreground;
    border: none;
    height: 1;
}
Footer > .footer--key         { color: $footer-key-foreground; background: $footer-key-background; text-style: bold; }
Footer > .footer--description { color: $footer-description-foreground; }

/* ═══════════════════════════════════════════════════════════════════════════
   TOP TELEMETRY & MARKET RIBBON (#top-status)
═══════════════════════════════════════════════════════════════════════════ */
#top-status {
    height: 3;
    background: $surface;
    color: $foreground;
    padding: 0;
    border-bottom: solid $border-blurred;
}

#account {
    height: 1;
    padding: 0 1;
    background: $surface;
    content-align: left middle;
}

#indices-bar {
    height: 1;
    background: $background;
    padding: 0 1;
    content-align: left middle;
}

#top-status-text {
    display: none;
}

/* ═══════════════════════════════════════════════════════════════════════════
   3-PANE INSTITUTIONAL WORKSPACE LAYOUT
═══════════════════════════════════════════════════════════════════════════ */
#workspace {
    height: 1fr;
    background: $background;
}

.pane {
    height: 100%;
    background: $background;
}

.panel-header {
    height: 1;
    background: $panel;
    color: $secondary;
    text-style: bold;
    content-align: left middle;
    padding: 0 1;
    margin: 0;
    border: none;
}

.pane-header {
    height: 1;
    background: $panel;
    color: $primary;
    text-style: bold;
    padding: 0 1;
    border: none;
}

.pane-sub-header {
    height: 1;
    background: $surface;
    color: $text-muted;
    text-style: bold;
    padding: 0 1;
    border: none;
}

/* Active pane focus illumination */
#left-pane:focus-within > #watchlist-panel > .panel-header {
    background: $primary-muted;
    color: $primary;
}
#center-pane:focus-within #symbol-header {
    background: $surface;
    border-bottom: solid $primary;
}
#right-pane:focus-within #desk-header {
    background: $primary-muted;
}
#status-pane:focus-within .panel-header {
    background: $primary-muted;
    color: $primary;
}
#command-pane:focus-within .panel-header {
    background: $primary-muted;
    color: $primary;
}

/* ── Left Pane: Watchlist & Market Pulse Scanner ─────────────────────────── */
#left-pane {
    width: 40;
    border-right: solid $border-blurred;
    background: $surface;
    padding: 0;
}

#watchlist-panel {
    height: 100%;
}

#t-watch {
    height: 1fr;
    min-height: 6;
}

#t-scanner {
    height: 6;
    min-height: 4;
    border: none;
}

/* ── Center Pane: Instrument Hero, Microstructure & Chart ────────────────── */
#center-pane {
    width: 1fr;
    border-right: solid $border-blurred;
    background: $background;
    padding: 0;
}

#symbol-focus-panel {
    height: 100%;
    background: $background;
    padding: 0;
    border: none;
}

#symbol-header {
    height: 3;
    background: $surface;
    border-bottom: solid $border-blurred;
    color: $foreground;
    text-style: bold;
    padding: 0 1;
    margin-top: 0;
    content-align: left middle;
}

#symbol-metrics {
    height: 2;
    background: $background;
    color: $text-muted;
    padding: 0 1;
    content-align: left middle;
}

#chart-panel {
    height: 1fr;
    min-height: 6;
    border: round $border-blurred;
    margin: 0 1;
    background: $background;
    padding: 0 1;
}

#stats-strip {
    height: 3;
    background: $surface;
    border-top: solid $border-blurred;
    color: $foreground;
    padding: 0 1;
    content-align: left middle;
}

/* ── Right Pane: Order Staging, Execution Desk & Risk Governance ─────────── */
#right-pane {
    width: 46;
    background: $surface;
    padding: 0;
}

#trade-panel {
    height: 100%;
}

#order-preview {
    background: $surface;
    border-bottom: solid $border-blurred;
    color: $foreground;
    padding: 0 1;
    height: 4;
}

#desk-header {
    height: 1;
    background: $panel;
    padding: 0 1;
    margin: 0;
    border: none;
}

#t-orders, #t-positions, #t-holdings, #t-funds {
    height: 1fr;
    min-height: 4;
}

#risk-summary {
    background: $surface;
    border-top: solid $border-blurred;
    color: $foreground;
    padding: 0 1;
    height: 4;
}

/* ── Bottom Row: Telemetry Stream & Command Palette Bar ──────────────────── */
#bottom-row {
    height: 8;
    min-height: 7;
    background: $background;
    border-top: solid $border-blurred;
}

#status-pane {
    width: 1fr;
    border-right: solid $border-blurred;
    padding: 0;
    background: $background;
}

#status-panel {
    height: 100%;
}

#status-log {
    height: 1fr;
    background: $background;
    color: $foreground;
    padding: 0 1;
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
    scrollbar-color-hover: $scrollbar-hover;
}

#command-pane {
    width: 50;
    padding: 0;
    background: $surface;
}

#command-panel {
    height: 100%;
}

#cmd-suggestions {
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}

#cmd-bar {
    height: 3;
    background: $surface;
    border: none;
}

#cmd-prefix {
    color: $block-cursor-foreground;
    text-style: bold;
    content-align: center middle;
    height: 3;
    width: 5;
    background: $primary;
    border: none;
}

#cmd-input {
    background: $background;
    border: solid $border-blurred;
    color: $foreground;
    height: 3;
}

#cmd-input:focus {
    border: solid $primary;
    background: $surface;
    color: $foreground;
}

#cmd-input .input--placeholder {
    color: $text-disabled;
}

#status {
    height: 1;
    padding: 0 1;
    dock: bottom;
    background: $background;
    color: $text-muted;
    content-align: left middle;
}

.hidden-data {
    display: none;
}

/* ── Legacy Sidebar / Card selectors for backward compatibility ──────────── */
#sidebar {
    width: 38;
    background: $background;
    border-right: solid $border-blurred;
}
#market-scanner-box, #action-order-box, #risk-summary-box {
    height: 6;
    background: $surface;
    padding: 0 1;
}
#pane-center { width: 1fr; background: $background; border-right: solid $border-blurred; }
#pane-right  { width: 1.2fr; background: $background; }

.nav-section-header {
    color: $primary;
    text-style: bold;
    padding: 0 2;
    margin-top: 1;
    background: $surface;
    border-top: solid $border-blurred;
    border-bottom: solid $border-blurred;
}
.nav-item { color: $text-muted; padding: 0 1; background: $surface; }
.nav-item:hover { color: $foreground; background: $panel; }
.nav-item-active {
    color: $primary;
    background: $primary-muted;
    border-left: tall $primary;
    padding: 0 2;
}
.nav-safety { color: $error; }
.nav-safety:hover { color: $error; text-style: bold; }
#content-area { width: 1fr; background: $background; }

/* ═══════════════════════════════════════════════════════════════════════════
   TABS
═══════════════════════════════════════════════════════════════════════════ */
TabbedContent { height: 1fr; margin: 0; }
TabbedContent > ContentSwitcher { border: none; }
TabPane { padding: 0; background: $background; }

Tabs { border-bottom: solid $border-blurred; background: $surface; height: 3; }
Tab  { color: $text-muted; padding: 0 3; height: 3; }
Tab:hover { color: $foreground; background: $panel; }
Tab.-active {
    color: $primary;
    text-style: bold;
    border-bottom: tall $primary;
    background: $surface;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DATA TABLES (HIGH-DENSITY INSTITUTIONAL GRID)
═══════════════════════════════════════════════════════════════════════════ */
DataTable {
    height: 1fr;
    border: none;
    background: $background;
    color: $foreground;
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
    scrollbar-color-hover: $scrollbar-hover;
}
DataTable > .datatable--header {
    background: $surface;
    color: $text-muted;
    text-style: bold;
    border-bottom: solid $border-blurred;
}
DataTable > .datatable--cursor {
    background: $panel;
    color: $foreground;
    text-style: bold;
}
DataTable:focus > .datatable--cursor {
    background: $primary-muted;
    color: $primary;
    text-style: bold;
}
DataTable > .datatable--hover    { background: $block-hover-background; }
DataTable > .datatable--even-row { background: $surface; }
DataTable > .datatable--odd-row  { background: $background; }
DataTable > .datatable--fixed    { background: $surface; color: $text-muted; }

/* ═══════════════════════════════════════════════════════════════════════════
   LOGS
═══════════════════════════════════════════════════════════════════════════ */
#feedlog {
    height: 12;
    border-top: tall $primary;
    background: $background;
    color: $success;
    padding: 0 1;
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
}
#activity-log {
    color: $text-muted;
    padding: 0 1;
    height: 1fr;
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODALS & OVERLAYS
═══════════════════════════════════════════════════════════════════════════ */
ModalScreen {
    align: center middle;
    background: $background 78%;
}

.modal {
    width: 116;
    max-width: 98%;
    height: auto;
    max-height: 94%;
    background: $surface;
    border: round $primary;
    padding: 1 3;
    overflow-y: auto;
}
.modal.wide    { width: 156; max-width: 98%; height: 90%; }
.theme-modal   { width: 96; max-width: 96%; height: 28; max-height: 92%; padding: 1 2; }
.confirm-modal { width: 78; max-width: 96%; height: auto; border: round $warning; }
.whatif-result {
    padding: 1 2;
    background: $background;
    border: round $border-blurred;
    margin: 1 0;
}

/* Focus Mode: Collapses peripheral panes so Symbol Focus & Chart take center stage */
Screen.focus-mode #sidebar,
Screen.focus-mode #indices-bar,
Screen.focus-mode #right-pane,
Screen.focus-mode #t-scanner {
    display: none;
}
Screen.focus-mode #left-pane {
    width: 30;
}

/* ── Order ticket two-panel layout ──────────────────────────────────────── */
.order-modal {
    width: 96%;
    max-width: 180;
    height: 90%;
    background: $surface;
    border: round $primary;
    overflow: hidden;
    padding: 0;
}
.order-left {
    width: 1fr;
    min-width: 56;
    height: 100%;
    padding: 1 3;
    border-right: solid $border-blurred;
    overflow-y: auto;
}
.order-right {
    width: 54;
    min-width: 40;
    height: 100%;
    padding: 1 2;
    background: $background;
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
    scrollbar-color-hover: $scrollbar-hover;
}

/* ── Chart modal ─────────────────────────────────────────────────────────── */
.modal.chart {
    width: 100%;
    max-width: 100%;
    height: 100%;
    max-height: 100%;
    background: $background;
    border: none;
    overflow: hidden;
    padding: 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODAL INTERNALS
═══════════════════════════════════════════════════════════════════════════ */
.title {
    text-style: bold;
    color: $primary;
    background: $panel;
    margin-bottom: 1;
    border-bottom: solid $border-blurred;
    padding: 0 1;
    height: 2;
    content-align: left middle;
}
.field-group-label {
    color: $text-muted;
    text-style: bold;
    margin: 1 0 0 0;
}
.section-label {
    color: $secondary;
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0;
    border-bottom: solid $border-blurred;
}
.confirm-body  {
    padding: 1 2;
    background: $background;
    border: round $border-blurred;
}
.row           { height: auto; margin-bottom: 1; }
.row > Input, .row > Select { width: 1fr; margin-right: 1; }
.field         { width: 1fr; height: auto; }
.field > Label { color: $text-muted; margin-bottom: 0; }
.buttons       { margin-top: 1; align: right middle; height: auto; }
.buttons > Button { margin-left: 1; min-width: 16; }
.err-msg       { color: $error; text-style: bold; margin-top: 1; }
.url-display   { color: $secondary; text-style: italic; padding: 0 1; margin-bottom: 1; }
.login-msg     { margin-top: 1; padding: 0 1; height: 2; content-align: left middle; }
.hint          { color: $text-muted; text-style: italic; margin-top: 0; }

/* ── Chart layout internals ──────────────────────────────────────────────── */
.chart-header-bar {
    height: 1;
    min-height: 1;
    background: $panel;
    border-bottom: solid $border-blurred;
    padding: 0 1;
}
.chart-title {
    color: $primary;
    text-style: bold;
    content-align: left middle;
    height: 1;
    width: auto;
}
.chart-meta-right {
    color: $text-muted;
    content-align: right middle;
    height: 1;
    width: 1fr;
}
.chart-interval-bar {
    height: 1;
    min-height: 1;
    background: $surface;
    border-bottom: solid $border-blurred;
    padding: 0 1;
}
.iv-pill {
    min-width: 4;
    height: 1;
    margin-right: 1;
    border: none;
    background: $panel;
    color: $text-muted;
    padding: 0 1;
}
.iv-pill:hover { background: $primary-muted; color: $primary; text-style: bold; }
.iv-pill.-primary {
    background: $primary;
    color: $background;
    text-style: bold;
    border: none;
}
.iv-action-pill {
    min-width: 5;
    height: 1;
    margin-left: 1;
    border: none;
    background: $surface;
    color: $secondary;
    padding: 0 1;
}
.iv-action-pill:hover { background: $secondary; color: $background; text-style: bold; }
.iv-buy-pill {
    min-width: 5;
    height: 1;
    margin-left: 1;
    border: none;
    background: $success;
    color: $background;
    text-style: bold;
    padding: 0 1;
}
.iv-sell-pill {
    min-width: 5;
    height: 1;
    margin-left: 1;
    border: none;
    background: $error;
    color: $background;
    text-style: bold;
    padding: 0 1;
}
.chart-divider { color: $border-blurred; width: 1; margin: 0 1; }
.iv-select { width: 18; height: 1; }
#chart-out {
    height: 1fr;
    min-height: 8;
    margin: 0;
    background: $background;
    color: $foreground;
    padding: 0;
}
.chart-bottom-bar {
    height: 1;
    min-height: 1;
    background: $panel;
    border-top: solid $border-blurred;
    padding: 0 1;
}
.chart-bottom-label {
    color: $secondary;
    text-style: bold;
    content-align: left middle;
    height: 1;
    width: 32;
}
.chart-bottom-hint {
    color: $text-muted;
    content-align: right middle;
    height: 1;
    width: 1fr;
}
#hist {
    height: 8;
    min-height: 4;
    border-top: solid $border-blurred;
}
#hist.hidden-drawer {
    display: none;
}
.chart-zen .chart-header-bar,
.chart-zen .chart-interval-bar,
.chart-zen .chart-bottom-bar,
.chart-zen #hist {
    display: none;
}
.sparkline { padding: 0 1; height: 3; content-align: center middle; }

/* ═══════════════════════════════════════════════════════════════════════════
   INPUTS & SELECTS
═══════════════════════════════════════════════════════════════════════════ */
Input {
    background: $background;
    border: solid $border-blurred;
    color: $foreground;
}
Input:focus {
    border: solid $primary;
    background: $surface;
}
Input .input--placeholder { color: $text-disabled; }

Select {
    background: $background;
    border: solid $border-blurred;
    color: $foreground;
}
Select:focus { border: solid $primary; }
Select > .select--arrow { color: $primary; }

Checkbox { color: $text-muted; }
Checkbox:focus { color: $primary; }

/* ═══════════════════════════════════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════════════════════════════════ */
Button {
    border: solid $border-blurred;
    min-width: 14;
    background: $background;
    color: $text-muted;
}
Button:hover {
    background: $panel;
    color: $foreground;
    border: solid $secondary;
}
Button.-primary {
    background: $primary-muted;
    color: $primary;
    text-style: bold;
    border: solid $primary;
}
Button.-primary:hover { background: $primary; color: $block-cursor-foreground; }
Button.-success {
    background: $success-muted;
    color: $success;
    text-style: bold;
    border: solid $success;
}
Button.-success:hover { background: $success; color: $block-cursor-foreground; }
Button.-error {
    background: $error-muted;
    color: $error;
    text-style: bold;
    border: solid $error;
}
Button.-error:hover { background: $error; color: $block-cursor-foreground; }

.btn-step {
    background: $background;
    color: $foreground;
    border: solid $border-blurred;
    width: 100%;
}
.btn-step:hover { background: $primary-muted; color: $primary; border: solid $primary; }
.btn-connect {
    background: $primary-muted;
    color: $primary;
    text-style: bold;
    border: solid $primary;
    width: 100%;
}
.btn-connect:hover { background: $primary; color: $block-cursor-foreground; }

/* ═══════════════════════════════════════════════════════════════════════════
   RULE
═══════════════════════════════════════════════════════════════════════════ */
Rule { color: $border-blurred; margin: 1 0; }

/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN WORKSTATION GATEWAY
═══════════════════════════════════════════════════════════════════════════ */
#login-container {
    align: center middle;
    background: $background;
    overflow-y: auto;
}
#login {
    width: 84;
    max-width: 96%;
    height: auto;
    padding: 1 4;
    border: round $primary;
    background: $surface;
}
#login-logo {
    color: $primary;
    text-align: center;
    text-style: bold;
    margin-bottom: 0;
}
#login Input, #login Select { margin-bottom: 1; width: 100%; }
.ip-display-card {
    background: $background;
    border: none;
    padding: 0 1;
    margin-bottom: 1;
    height: 1;
}
.buttons-bar { height: auto; margin-top: 1; }
.buttons-bar > Button { margin-right: 1; width: 1fr; }

/* ═══════════════════════════════════════════════════════════════════════════
   WATCHLIST MINI-SPARKLINES & PNL STRIP
═══════════════════════════════════════════════════════════════════════════ */
.mini-spark-up   { color: $success; }
.mini-spark-down { color: $error; }
.mini-spark-flat { color: $text-muted; }

#pnl-strip {
    height: 1;
    background: $surface;
    border-top: solid $border-blurred;
    padding: 0 1;
    content-align: left middle;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD & INTERVAL PILLS & QUOTE BANNER
═══════════════════════════════════════════════════════════════════════════ */
#dash-container {
    height: 1fr;
    padding: 1 2;
    background: $background;
}
#dash-summary-strip {
    background: $surface;
    border: round $border-blurred;
    padding: 1 2;
    margin-bottom: 1;
    height: auto;
}
#dash-dual-panel {
    height: auto;
    margin-bottom: 1;
}
#dash-left-box {
    width: 1fr;
    background: $surface;
    border: round $border-blurred;
    padding: 1 2;
    margin-right: 1;
}
#dash-right-box {
    width: 1fr;
    background: $surface;
    border: round $border-blurred;
    padding: 1 2;
}
#dash-feed-log {
    height: 14;
    background: $surface;
    border: round $border-blurred;
    padding: 0 1;
}

.chart-interval-pills {
    height: auto;
    padding: 0 1;
    background: $surface;
}
.btn-pill {
    min-width: 6;
    height: 1;
    margin-right: 1;
    border: none;
    background: $panel;
    color: $text-muted;
}
.btn-pill:hover {
    background: $primary-muted;
    color: $primary;
}

#order-quote-banner {
    background: $background;
    border: round $border-blurred;
    padding: 0 1;
    margin-bottom: 1;
    height: 3;
    content-align: left middle;
}
#btn-fill-price {
    margin-bottom: 1;
    min-width: 12;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SCROLLBAR
═══════════════════════════════════════════════════════════════════════════ */
VerticalScroll {
    scrollbar-background: $scrollbar-background;
    scrollbar-color: $scrollbar;
    scrollbar-color-hover: $scrollbar-hover;
}

/* ═══════════════════════════════════════════════════════════════════════════
   RESPONSIVE LAYOUT BREAKPOINTS
   width  : -xs (<90)  -sm (90-119)  -md (120-159)  -lg (160-199)  -xl (200+)
   height : -short (<30)  -medium (30-44)  -tall (45+)
═══════════════════════════════════════════════════════════════════════════ */
Screen.-xs #sidebar, Screen.-sm #sidebar { display: none; }
Screen.-xs #left-pane  { width: 28; }
Screen.-sm #left-pane  { width: 32; }
Screen.-md #left-pane  { width: 38; }
Screen.-lg #left-pane  { width: 42; }
Screen.-xl #left-pane  { width: 48; }

Screen.-xs #right-pane { width: 30; }
Screen.-sm #right-pane { width: 36; }
Screen.-md #right-pane { width: 44; }
Screen.-lg #right-pane { width: 50; }
Screen.-xl #right-pane { width: 58; }

Screen.-xs #command-pane { width: 34; }
Screen.-sm #command-pane { width: 40; }
Screen.-md #command-pane { width: 48; }
Screen.-lg #command-pane { width: 56; }
Screen.-xl #command-pane { width: 64; }

Screen.-xs Tab, Screen.-sm Tab { padding: 0 1; }
Screen.-md Tab { padding: 0 2; }

Screen.-xs #dash-dual-panel, Screen.-sm #dash-dual-panel { layout: vertical; }
Screen.-xs #dash-left-box, Screen.-sm #dash-left-box {
    width: 100%;
    margin-right: 0;
    margin-bottom: 1;
}
Screen.-xs #dash-right-box, Screen.-sm #dash-right-box { width: 100%; }
Screen.-xs #dash-container { padding: 0 1; }
Screen.-xs #dash-summary-strip,
Screen.-xs #dash-left-box,
Screen.-xs #dash-right-box { padding: 0 1; }

/* ── Short terminals (<30 rows): ultra-compact chrome to maximize data ───── */
Screen.-short Header { height: 1; border-bottom: none; }
Screen.-short #top-status { height: 1; }
Screen.-short #account { height: 1; border-bottom: none; padding: 0 1; }
Screen.-short #indices-bar { display: none; }
Screen.-short #symbol-header { height: 1; border: none; }
Screen.-short #symbol-metrics { height: 1; }
Screen.-short #stats-strip { height: 1; border-top: none; }
Screen.-short #order-preview { height: 3; }
Screen.-short #risk-summary { height: 3; }
Screen.-short #t-scanner { height: 4; }
Screen.-short #bottom-row { height: 5; min-height: 5; }
Screen.-short #cmd-suggestions { display: none; }
Screen.-short #pnl-strip { height: 1; border-top: none; }
Screen.-short #status { height: 1; border-top: none; }
Screen.-short #cmd-bar { height: 1; border: none; }
Screen.-short #cmd-prefix { height: 1; border-right: none; }
Screen.-short #cmd-input { height: 1; }
Screen.-short Tabs { height: 2; }
Screen.-short Tab { height: 2; }
Screen.-short #feedlog { height: 6; }
Screen.-short #dash-feed-log { height: 4; }
Screen.-short .nav-section-header { margin-top: 0; }
Screen.-medium #indices-bar { height: 1; border-bottom: none; }
Screen.-medium #feedlog { height: 8; }
Screen.-medium #dash-feed-log { height: 6; }
"""
