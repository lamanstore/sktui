"""Textual CSS styles for SKTUI — premium dark trading-terminal theme."""
from __future__ import annotations

CSS = """
/* ═══════════════════════════════════════════════════════════════════════════
   BASE / RESET
═══════════════════════════════════════════════════════════════════════════ */
Screen {
    background: #060810;
    color: #d4d4d8;
    layers: base overlay;
}

/* ═══════════════════════════════════════════════════════════════════════════
   HEADER & FOOTER
═══════════════════════════════════════════════════════════════════════════ */
Header {
    background: #0a0d18;
    color: #00e5ff;
    text-style: bold;
    border-bottom: tall #0f1929;
    height: 3;
}
Header > .header--title     { color: #00e5ff; text-style: bold; }
Header > .header--sub-title { color: #334155; }

Footer {
    background: #0a0d18;
    color: #334155;
    border-top: solid #0f1929;
    height: 1;
}
Footer > .footer--key       { color: #00e5ff; text-style: bold; }
Footer > .footer--description { color: #475569; }

/* ═══════════════════════════════════════════════════════════════════════════
   ACCOUNT / TICKER BAR
═══════════════════════════════════════════════════════════════════════════ */
#account {
    height: 3;
    padding: 0 2;
    background: #080c16;
    border-bottom: solid #0f1929;
    content-align: left middle;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MARKET INDICES TICKER
═══════════════════════════════════════════════════════════════════════════ */
#indices-bar {
    height: 2;
    background: #050810;
    border-bottom: solid #0f1929;
    padding: 0 2;
    content-align: left middle;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SYMBOL FOCUS PANEL
/* ═══════════════════════════════════════════════════════════════════════════
   WORKSPACE 3-PANE LAYOUT
═══════════════════════════════════════════════════════════════════════════ */
#workspace {
    height: 1fr;
    background: #060810;
}

.pane {
    height: 100%;
    background: #060810;
}

.pane-header {
    height: 1;
    background: #0a0e1c;
    color: #00e5ff;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #0f1929;
}

.pane-sub-header {
    height: 1;
    background: #080c16;
    color: #64748b;
    text-style: bold;
    padding: 0 1;
    border-top: solid #0f1929;
    border-bottom: solid #0f1929;
}

/* ── Left Pane: Watchlist & Scanner ──────────────────────────────────────── */
#sidebar {
    width: 38;
    background: #060810;
    border-right: solid #0f1929;
}

#sidebar #t-watch {
    height: 1fr;
    min-height: 8;
}

#market-scanner-box {
    height: 6;
    background: #080c16;
    padding: 0 1;
}

/* ── Center Pane: Selected Symbol Hero & Order Action ────────────────────── */
#pane-center {
    width: 1fr;
    background: #060810;
    border-right: solid #0f1929;
}

#symbol-focus-panel {
    height: 1fr;
    min-height: 8;
    background: #080d1a;
    padding: 1 1;
    border: none;
}

#action-order-box {
    height: 6;
    background: #080c16;
    padding: 0 1;
}

/* ── Right Pane: Desk Execution & Risk Governance ────────────────────────── */
#pane-right {
    width: 1.2fr;
    background: #060810;
}

#pane-right TabbedContent {
    height: 1fr;
}

#risk-summary-box {
    height: 6;
    background: #080c16;
    padding: 0 1;
}

/* ═══════════════════════════════════════════════════════════════════════════
   FIXED 3-PANE WORKSPACE REDESIGN (CLEAN & TERMINAL-FIRST)
═══════════════════════════════════════════════════════════════════════════ */
#top-status {
    height: 3;
    content-align: left middle;
    background: #0a0e1c;
    color: #cbd5e1;
    padding: 0 1;
    border-bottom: solid #1e293b;
}

#left-pane {
    width: 32;
    border-right: solid #1e293b;
    background: #070c18;
    padding: 0 1;
}

#center-pane {
    width: 1fr;
    border-right: solid #1e293b;
    background: #080d1a;
    padding: 0 1;
}

#right-pane {
    width: 38;
    background: #070c18;
    padding: 0 1;
}

#bottom-row {
    height: 9;
    min-height: 8;
    background: #060912;
    border-top: solid #1e293b;
}

#status-pane {
    width: 1fr;
    border-right: solid #1e293b;
    padding: 0 1;
}

#command-pane {
    width: 38;
    padding: 0 1;
}

.panel-header {
    color: #00e5ff;
    text-style: bold;
    content-align: left middle;
    margin: 0;
    height: 1;
}

#symbol-header {
    color: #f8fafc;
    text-style: bold;
    padding: 0 0;
}

#symbol-metrics {
    color: #94a3b8;
    padding: 0 0;
}

#chart-panel {
    height: 1fr;
    min-height: 5;
    border: solid #1e293b;
    margin: 1 0;
    background: #050812;
    padding: 0 1;
}

#stats-strip {
    color: #cbd5e1;
    padding: 0 0;
}

#order-preview {
    background: #0a1122;
    border: solid #1e293b;
    color: #d4d4d8;
    padding: 0 1;
    height: 6;
}

#risk-summary {
    background: #0a1122;
    border: solid #1e293b;
    color: #d4d4d8;
    padding: 0 1;
    height: 5;
}

#status-log {
    height: 1fr;
    background: #050810;
}

.hidden-data {
    display: none;
}

#desk-header {
    height: 1;
    margin: 1 0 0 0;
}

#t-watch, #t-scanner, #t-positions, #t-orders, #t-holdings, #t-funds {
    height: 1fr;
    min-height: 4;
}


.nav-section-header {
    color: #00e5ff;
    text-style: bold;
    padding: 0 2;
    margin-top: 1;
    background: #050810;
    border-top: solid #0f1929;
    border-bottom: solid #0f1929;
}
.nav-item {
    color: #475569;
    padding: 0 1;
    background: #080c16;
}
.nav-item:hover {
    color: #94a3b8;
    background: #0d1526;
}
.nav-item-active {
    color: #00e5ff;
    background: #0a1f36;
    border-left: tall #00e5ff;
    padding: 0 2;
}
.nav-safety   { color: #7f1d1d; }
.nav-safety:hover { color: #ef4444; }

/* ═══════════════════════════════════════════════════════════════════════════
   CONTENT AREA
═══════════════════════════════════════════════════════════════════════════ */
#content-area { width: 1fr; background: #060810; }

/* ═══════════════════════════════════════════════════════════════════════════
   TABS
═══════════════════════════════════════════════════════════════════════════ */
TabbedContent { height: 1fr; margin: 0; }
TabbedContent > ContentSwitcher { border: none; }
TabPane { padding: 0; background: #060810; }

Tabs { border-bottom: solid #0f1929; background: #080c16; height: 3; }
Tab  { color: #334155; padding: 0 3; height: 3; }
Tab:hover { color: #64748b; background: #0a0f1e; }
Tab.-active {
    color: #00e5ff;
    text-style: bold;
    border-bottom: tall #00e5ff;
    background: #080c16;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DATA TABLES
═══════════════════════════════════════════════════════════════════════════ */
DataTable {
    height: 1fr;
    border: none;
    background: #060810;
    scrollbar-background: #080c16;
    scrollbar-color: #1e3a5f;
    scrollbar-color-hover: #00e5ff;
}
DataTable > .datatable--header {
    background: #080c16;
    color: #00e5ff;
    text-style: bold;
    border-bottom: solid #0f1929;
}
DataTable > .datatable--cursor {
    background: #0a1f36;
    color: #f1f5f9;
    text-style: bold;
}
DataTable > .datatable--hover  { background: #0d1526; }
DataTable > .datatable--even-row { background: #070a12; }
DataTable > .datatable--fixed  { background: #080c16; color: #94a3b8; }

/* ═══════════════════════════════════════════════════════════════════════════
   COMMAND BAR
═══════════════════════════════════════════════════════════════════════════ */
#cmd-suggestions {
    height: 1;
    background: #060912;
    color: #94a3b8;
    padding: 0 1;
}
#cmd-bar {
    height: 3;
    background: #080c16;
    border-top: solid #0f1929;
}
#cmd-prefix {
    color: #00e5ff;
    text-style: bold;
    content-align: center middle;
    height: 3;
    width: 5;
    background: #0a1f36;
    border-right: solid #0f1929;
}
#cmd-input {
    background: #080c16;
    border: none;
    color: #475569;
    height: 3;
}
#cmd-input:focus {
    border: none;
    background: #0a0d18;
    color: #d4d4d8;
}
#cmd-input .input--placeholder { color: #1e3a5f; }

/* ═══════════════════════════════════════════════════════════════════════════
   STATUS BAR
═══════════════════════════════════════════════════════════════════════════ */
#status {
    height: 2;
    padding: 0 2;
    dock: bottom;
    background: #060810;
    border-top: solid #0f1929;
    color: #334155;
    content-align: left middle;
}

/* ═══════════════════════════════════════════════════════════════════════════
   LOGS
═══════════════════════════════════════════════════════════════════════════ */
#feedlog {
    height: 12;
    border-top: tall #00e5ff;
    background: #060810;
    color: #10b981;
    padding: 0 1;
    scrollbar-background: #080c16;
    scrollbar-color: #1e3a5f;
}
#activity-log {
    color: #475569;
    padding: 0 1;
    height: 1fr;
    scrollbar-background: #080c16;
    scrollbar-color: #1e3a5f;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODALS
═══════════════════════════════════════════════════════════════════════════ */
ModalScreen { align: center middle; }

.modal {
    width: 120;
    max-width: 100%;
    height: auto;
    max-height: 94%;
    background: #080c16;
    border: tall #00e5ff;
    padding: 2 4;
    overflow-y: auto;
}
.modal.wide    { width: 160; max-width: 98%; height: 90%; }
.confirm-modal { width: 82; max-width: 98%; height: auto; }
.whatif-result { padding: 1 0; }

Screen.focus-mode #sidebar, Screen.focus-mode #indices-bar {
    display: none;
}

/* ── Order ticket two-panel layout ──────────────────────────────────────── */
.order-modal {
    width: 98%;
    max-width: 200;
    height: 90%;
    background: #080c16;
    border: tall #00e5ff;
    overflow: hidden;
}
.order-left {
    width: 1fr;
    min-width: 60;
    height: 100%;
    padding: 1 3;
    border-right: solid #0f1929;
    overflow-y: auto;
}
.order-right {
    width: 55;
    min-width: 42;
    height: 100%;
    padding: 1 2;
    background: #050810;
    scrollbar-background: #080c16;
    scrollbar-color: #1e3a5f;
    scrollbar-color-hover: #00e5ff;
}

/* ── Chart modal ─────────────────────────────────────────────────────────── */
.modal.chart {
    width: 98%;
    max-width: 200;
    height: 95%;
    max-height: 98%;
    background: #080c16;
    border: tall #00e5ff;
    overflow: hidden;
    padding: 0;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODAL INTERNALS
═══════════════════════════════════════════════════════════════════════════ */
.title {
    text-style: bold;
    color: #00e5ff;
    margin-bottom: 1;
    border-bottom: solid #0f1929;
    padding-bottom: 1;
}
.field-group-label {
    color: #334155;
    text-style: italic;
    margin: 1 0 0 0;
}
.section-label {
    color: #00e5ff;
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0 0 0 0;
    border-bottom: solid #0f1929;
}
.confirm-body  { padding: 1 0; }
.row           { height: auto; margin-bottom: 1; }
.row > Input, .row > Select { width: 1fr; margin-right: 1; }
.field         { width: 1fr; height: auto; }
.field > Label { color: #475569; margin-bottom: 0; }
.buttons       { margin-top: 1; align: right middle; }
.buttons > Button { margin-left: 2; min-width: 20; }
.err-msg       { color: #ef4444; margin-top: 1; }
.url-display   { color: #334155; text-style: italic; padding: 0 1; margin-bottom: 1; }
.login-msg     { margin-top: 1; padding: 0 1; height: 3; }
.hint          { color: #334155; text-style: italic; margin-top: 1; }

/* ── Chart layout internals ──────────────────────────────────────────────── */
.chart-header-bar {
    height: 2;
    background: #050810;
    border-bottom: solid #0f1929;
    padding: 0 2;
}
.chart-title {
    color: #00e5ff;
    text-style: bold;
    content-align: left middle;
    height: 2;
    width: 1fr;
}
.chart-meta-right {
    color: #475569;
    text-style: italic;
    content-align: right middle;
    height: 2;
    width: 1fr;
}
.chart-interval-bar {
    height: 3;
    background: #080c16;
    border-bottom: solid #0f1929;
    padding: 0 1;
}
.iv-pill {
    min-width: 5;
    height: 3;
    margin-right: 0;
    border: none;
    background: #0d1526;
    color: #64748b;
    padding: 0 1;
}
.iv-pill:hover { background: #0a1f36; color: #00e5ff; }
.iv-pill.-primary { background: #0a1f36; color: #00e5ff; text-style: bold; border: none; }
.chart-divider { color: #0f1929; width: 1; margin: 0 1; }
.iv-select { width: 18; height: 3; }
#chart-out {
    height: 1fr;
    min-height: 10;
    margin: 0;
}
.chart-bottom-bar {
    height: 2;
    background: #050810;
    border-top: solid #0f1929;
    padding: 0 1;
}
.chart-bottom-label {
    color: #00e5ff;
    text-style: bold;
    content-align: left middle;
    height: 2;
    width: 30;
}
.chart-bottom-hint {
    color: #334155;
    text-style: italic;
    content-align: left middle;
    height: 2;
    width: 1fr;
}
#hist {
    height: 12;
    min-height: 8;
    border-top: none;
}
.sparkline { padding: 0 1; height: 3; content-align: center middle; }

/* ═══════════════════════════════════════════════════════════════════════════
   INPUTS & SELECTS
═══════════════════════════════════════════════════════════════════════════ */
Input  { background: #0d1526; border: solid #1e3a5f; color: #d4d4d8; }
Input:focus { border: tall #00e5ff; background: #0a1428; }
Input .input--placeholder { color: #1e3a5f; }

Select { background: #0d1526; border: solid #1e3a5f; }
Select:focus  { border: tall #00e5ff; }
Select > .select--arrow { color: #00e5ff; }

Checkbox { color: #64748b; }
Checkbox:focus { color: #00e5ff; }

/* ═══════════════════════════════════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════════════════════════════════ */
Button { border: solid #1e3a5f; min-width: 14; background: #0d1526; color: #64748b; }
Button:hover { background: #0a1f36; color: #94a3b8; }
Button.-primary {
    background: #0a1f36;
    color: #00e5ff;
    text-style: bold;
    border: solid #00e5ff;
}
Button.-primary:hover { background: #0d2a4a; }
Button.-success { background: #052e22; color: #10b981; border: solid #10b981; }
Button.-success:hover { background: #063d2e; }
Button.-error   { background: #3a0808; color: #ef4444; border: solid #ef4444; }
Button.-error:hover   { background: #4d0c0c; }

.btn-step    { background: #0d1526; color: #64748b; border: solid #1e3a5f; width: 100%; }
.btn-step:hover { background: #0a1f36; color: #94a3b8; }
.btn-connect { background: #0a1f36; color: #00e5ff; text-style: bold;
               border: solid #00e5ff; width: 100%; }
.btn-connect:hover { background: #0d2a4a; }

/* ═══════════════════════════════════════════════════════════════════════════
   RULE
═══════════════════════════════════════════════════════════════════════════ */
Rule { color: #0f1929; margin: 1 0; }

/* ═══════════════════════════════════════════════════════════════════════════
   LOGIN
═══════════════════════════════════════════════════════════════════════════ */
#login-container {
    align: center middle;
    background: #060810;
    overflow: hidden;
}
#login {
    width: 82;
    max-width: 96%;
    height: auto;
    padding: 2 4;
    border: tall #00e5ff;
    background: #080c16;
}
#login-logo {
    color: #00e5ff;
    text-align: center;
    text-style: bold;
    margin-bottom: 0;
}
#login Input, #login Select { margin-bottom: 1; width: 100%; }
.ip-display-card {
    background: #050810;
    border: solid #0f1929;
    padding: 0 1;
    margin-bottom: 1;
}
.buttons-bar { height: auto; margin-top: 1; }
.buttons-bar > Button { margin-right: 1; width: 1fr; }

/* ═══════════════════════════════════════════════════════════════════════════
   WATCHLIST MINI-SPARKLINES (per row)
═══════════════════════════════════════════════════════════════════════════ */
.mini-spark-up   { color: #10b981; }
.mini-spark-down { color: #ef4444; }
.mini-spark-flat { color: #334155; }

/* ═══════════════════════════════════════════════════════════════════════════
   PNL SUMMARY STRIP
═══════════════════════════════════════════════════════════════════════════ */
#pnl-strip {
    height: 2;
    background: #070a12;
    border-top: solid #0f1929;
    padding: 0 2;
    content-align: left middle;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD & INTERVAL PILLS & QUOTE BANNER
═══════════════════════════════════════════════════════════════════════════ */
#dash-container {
    height: 1fr;
    padding: 1 2;
    background: #060810;
}
#dash-summary-strip {
    background: #080c16;
    border: solid #0f1929;
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
    background: #080c16;
    border: solid #0f1929;
    padding: 1 2;
    margin-right: 1;
}
#dash-right-box {
    width: 1fr;
    background: #080c16;
    border: solid #0f1929;
    padding: 1 2;
}
#dash-feed-log {
    height: 14;
    background: #080c16;
    border: solid #0f1929;
    padding: 0 1;
}

.chart-interval-pills {
    height: auto;
    padding: 0 1;
    background: #080c16;
}
.btn-pill {
    min-width: 6;
    height: 1;
    margin-right: 1;
    border: none;
    background: #0d1526;
    color: #94a3b8;
}
.btn-pill:hover {
    background: #0a1f36;
    color: #00e5ff;
}

#order-quote-banner {
    background: #080c16;
    border-bottom: solid #0f1929;
    padding: 1 2;
    margin-bottom: 1;
}
#btn-fill-price {
    margin-bottom: 1;
    min-width: 28;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SCROLLBAR
═══════════════════════════════════════════════════════════════════════════ */
VerticalScroll {
    scrollbar-background: #080c16;
    scrollbar-color: #1e3a5f;
    scrollbar-color-hover: #00e5ff;
}

/* ═══════════════════════════════════════════════════════════════════════════
   RESPONSIVE LAYOUT
   Screen classes are applied automatically by Textual from
   SKApp.HORIZONTAL_BREAKPOINTS / VERTICAL_BREAKPOINTS:
     width  : -xs (<80)  -sm (80-109)  -md (110-149)  -lg (150-199)  -xl (200+)
     height : -short (<30)  -medium (30-44)  -tall (45+)
═══════════════════════════════════════════════════════════════════════════ */

/* ── Sidebar: scale with width, hide on narrow terminals ─────────────────── */
Screen.-xs #sidebar, Screen.-sm #sidebar { display: none; }
Screen.-md #sidebar { width: 22; }
Screen.-lg #sidebar { width: 28; }
Screen.-xl #sidebar { width: 34; }

/* ── Tabs: tighter padding when horizontal space is limited ─────────────── */
Screen.-xs Tab, Screen.-sm Tab { padding: 0 1; }
Screen.-md Tab { padding: 0 2; }

/* ── Dashboard: stack the two panels vertically on narrow screens ────────── */
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

/* ── Short terminals: collapse chrome to maximise data rows ─────────────── */
Screen.-short Header { height: 1; border-bottom: none; }
Screen.-short #account { height: 1; border-bottom: none; padding: 0 1; }
Screen.-short #indices-bar { display: none; }
Screen.-short #symbol-focus-panel { height: 2; border-bottom: none; }
Screen.-short #cmd-suggestions { display: none; }
Screen.-short #pnl-strip { height: 1; border-top: none; }
Screen.-short #status { height: 1; border-top: none; }
Screen.-short #cmd-bar { height: 1; border-top: none; }
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
Screen.-tall #dash-feed-log { height: 8; }

/* ── Modals: reclaim padding and go full-bleed on small terminals ───────── */
ModalScreen.-xs .modal, ModalScreen.-sm .modal {
    width: 100%;
    max-width: 100%;
    padding: 1 1;
}
ModalScreen.-xs .confirm-modal, ModalScreen.-sm .confirm-modal {
    width: 98%;
    padding: 1 2;
}
ModalScreen.-xs .modal .row > Button, ModalScreen.-sm .modal .row > Button {
    min-width: 8;
    padding: 0 1;
    margin-right: 1;
}
ModalScreen.-md .modal { padding: 1 2; }
ModalScreen.-short .modal {
    max-height: 100%;
    padding: 0 1;
}
ModalScreen.-short .modal.wide { height: 100%; }
ModalScreen.-short .title { margin-bottom: 0; padding-bottom: 0; }
ModalScreen.-short Rule { margin: 0; }
ModalScreen.-xs .buttons > Button, ModalScreen.-sm .buttons > Button {
    min-width: 10;
    margin-left: 1;
}
ModalScreen.-xs Button { min-width: 8; }

/* ── Order ticket: stack panels vertically below ~110 columns ───────────── */
ModalScreen.-xs .order-modal, ModalScreen.-sm .order-modal {
    layout: vertical;
    width: 100%;
    height: 100%;
    overflow-y: auto;
}
ModalScreen.-xs .order-left, ModalScreen.-sm .order-left {
    width: 100%;
    min-width: 0;
    height: auto;
    padding: 0 1;
    border-right: none;
    border-bottom: solid #0f1929;
    overflow: hidden;
}
ModalScreen.-xs .order-right, ModalScreen.-sm .order-right {
    width: 100%;
    min-width: 0;
    height: auto;
    padding: 0 1;
}
ModalScreen.-md .order-right { width: 46; }
ModalScreen.-short .order-modal { height: 100%; }

/* ── Chart modal: adapt canvas, history table and hint bar ───────────────── */
ModalScreen.-xs .modal.chart, ModalScreen.-sm .modal.chart { width: 100%; }
ModalScreen.-short .modal.chart { height: 100%; max-height: 100%; }
ModalScreen.-xs .chart-bottom-hint, ModalScreen.-sm .chart-bottom-hint { display: none; }
ModalScreen.-xs .chart-bottom-label, ModalScreen.-sm .chart-bottom-label { width: 1fr; }
ModalScreen.-xs .iv-pill { min-width: 4; padding: 0; }
ModalScreen.-short #hist { display: none; }
ModalScreen.-short .chart-bottom-bar { display: none; }
ModalScreen.-medium #hist { height: 7; min-height: 5; }
ModalScreen.-tall #hist { height: 12; }

/* ── Login: full-width card on narrow, compact on short ──────────────────── */
Screen.-xs #login { width: 100%; padding: 0 1; }
Screen.-short #login-logo { display: none; }
"""

