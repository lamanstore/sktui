"""Textual CSS styles for SKTUI."""
from __future__ import annotations

CSS = """
/* ─── Base ──────────────────────────────────────────────────────── */
Screen { background: #09090b; color: #e4e4e7; }

/* ─── Header & Footer ───────────────────────────────────────────── */
Header { background: #0c0c0f; color: #00f0ff; text-style: bold;
         border-bottom: tall #1a1a20; height: 3; }
Header > .header--title     { color: #00f0ff; text-style: bold; }
Header > .header--sub-title { color: #52525b; }
Footer { background: #0c0c0f; color: #52525b; border-top: solid #1a1a20; }
Footer > .footer--key { color: #00f0ff; text-style: bold; }

/* ─── Account bar ───────────────────────────────────────────────── */
#account { height: 3; padding: 0 2; background: #111115;
           border-bottom: solid #1a1a20; content-align: left middle; }

/* ─── Main body ─────────────────────────────────────────────────── */
#main-body { height: 1fr; }

/* ─── Sidebar ───────────────────────────────────────────────────── */
#sidebar { width: 22; background: #0c0c0f;
           border-right: solid #1a1a20; }
#nav     { width: 22; height: 1fr; background: #0c0c0f; padding: 1 0; }
.nav-section-header { color: #3f3f46; text-style: bold;
                      padding: 1 2 0 2; }
.nav-item        { color: #52525b; padding: 0 2; }
.nav-safety      { color: #7f1d1d; }

/* ─── Content area ──────────────────────────────────────────────── */
#content-area { width: 1fr; }

/* ─── Tabs ──────────────────────────────────────────────────────── */
TabbedContent { height: 1fr; margin: 0; }
TabbedContent > ContentSwitcher { border: none; }
TabPane { padding: 0; }
Tabs { border-bottom: solid #1a1a20; background: #0c0c0f; }
Tab { color: #3f3f46; padding: 1 3; }
Tab.-active { color: #00f0ff; text-style: bold;
              border-bottom: tall #00f0ff; background: #111115; }

/* ─── DataTable ─────────────────────────────────────────────────── */
DataTable { height: 1fr; border: none; background: #09090b; }
DataTable > .datatable--header    { background: #0c0c0f; color: #00f0ff;
                                    text-style: bold; }
DataTable > .datatable--cursor    { background: #0f2030; color: #e4e4e7;
                                    text-style: bold; }
DataTable > .datatable--hover     { background: #111115; }
DataTable > .datatable--even-row  { background: #0b0b0e; }

/* ─── Command bar ───────────────────────────────────────────────── */
#cmd-bar    { height: 3; background: #0c0c0f; border-top: solid #1a1a20; }
#cmd-prefix { color: #00f0ff; text-style: bold; content-align: center middle;
              height: 3; width: 5; background: #111115;
              border-right: solid #1a1a20; }
#cmd-input  { background: #0c0c0f; border: none; color: #71717a; height: 3; }
#cmd-input:focus { border: none; background: #111115; color: #e4e4e7; }

/* ─── Status bar ────────────────────────────────────────────────── */
#status { height: 3; padding: 0 2; dock: bottom; background: #09090b;
          border-top: solid #1a1a20; color: #52525b;
          content-align: left middle; }

/* ─── Feed / activity logs ──────────────────────────────────────── */
#feedlog      { height: 10; border-top: tall #00f0ff; background: #09090b;
                color: #10b981; padding: 0 1; }
#activity-log { color: #71717a; padding: 0 1; height: 1fr; }

/* ─── Modals ────────────────────────────────────────────────────── */
ModalScreen { align: center middle; }
.modal { width: 110; max-width: 100%; height: auto; max-height: 92%;
         background: #0e0e12; border: tall #00f0ff; padding: 2 4; }
.modal.wide   { width: 148; height: 88%; }
.confirm-modal { width: 80; height: auto; }
.whatif-result { padding: 1 0; }

/* ─── Modal internals ───────────────────────────────────────────── */
.title { text-style: bold; color: #00f0ff; margin-bottom: 1;
         border-bottom: solid #1a1a20; padding-bottom: 1; }
.field-group-label { color: #52525b; text-style: italic; margin: 1 0 0 0; }
.section-label     { color: #52525b; text-style: italic; margin-bottom: 0; }
.confirm-body      { padding: 1 0; }
.row               { height: auto; margin-bottom: 1; }
.row > Input, .row > Select { width: 1fr; margin-right: 1; }
.field             { width: 1fr; height: auto; }
.field > Label     { color: #52525b; margin-bottom: 0; }
.buttons           { margin-top: 2; align: right middle; }
.buttons > Button  { margin-left: 2; min-width: 20; }
.sparkline         { padding: 0 1; height: 3; content-align: center middle; }
.err-msg           { color: #ef4444; margin-top: 1; }
.url-display       { color: #52525b; text-style: italic;
                     padding: 0 1; margin-bottom: 1; }
.login-msg         { margin-top: 1; padding: 0 1; height: 3; }
.hint              { color: #52525b; text-style: italic; margin-top: 1; }

/* ─── Inputs & Selects ──────────────────────────────────────────── */
Input  { background: #18181b; border: solid #27272a; color: #e4e4e7; }
Input:focus { border: tall #00f0ff; }
Select { background: #18181b; border: solid #27272a; }
Select:focus { border: tall #00f0ff; }
Checkbox { color: #a1a1aa; }

/* ─── Buttons ───────────────────────────────────────────────────── */
Button { border: solid #27272a; min-width: 14; }
Button.-primary { background: #0b3a4d; color: #00f0ff;
                  text-style: bold; border: solid #00f0ff; }
Button.-success { background: #052e22; color: #10b981; border: solid #10b981; }
Button.-error   { background: #3a0808; color: #ef4444; border: solid #ef4444; }
.btn-step    { background: #111115; color: #71717a;
               border: solid #27272a; width: 100%; }
.btn-connect { background: #0b3a4d; color: #00f0ff; text-style: bold;
               border: solid #00f0ff; width: 100%; }

/* ─── Rule ──────────────────────────────────────────────────────── */
Rule { color: #1a1a20; margin: 1 0; }

/* ─── Login ─────────────────────────────────────────────────────── */
#login-container { align: center middle; background: #09090b; overflow: hidden; }
#login { width: 80; max-width: 96%; height: auto; padding: 1 3;
         border: tall #00f0ff; background: #0e0e12; }
#login-logo { color: #00f0ff; text-align: center;
              text-style: bold; margin-bottom: 0; }
#login Input, #login Select { margin-bottom: 1; width: 100%; }
.buttons-bar { height: auto; margin-top: 1; }
.buttons-bar > Button { margin-right: 1; width: 1fr; }
"""
