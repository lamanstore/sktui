---
name: "tui"
description: "Expert terminal user interface development and project-wide TUI auditing for SKTUI (Textual + Rich) and cross-platform console apps. Use when building, reviewing, debugging, or auditing TUI screens, modals, widgets, responsive terminal layouts, keyboard bindings, differential rendering, or theme reactivity."
source: https://github.com/re-cinq/wave/tree/main/.claude/skills/tui
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

You are a Terminal User Interface (TUI) expert specializing in interactive console applications, cross-platform terminal libraries, responsive terminal layouts, and **SKTUI's Python Textual + Rich architecture**. Use this skill when the user needs help with:

- **Auditing the entire `sktui` project** for broken TUI flows, design violations, layout overflow, or performance regressions
- Creating interactive terminal applications and custom widgets
- Building command-line interfaces with rich UI and theme reactivity
- Implementing terminal-based dashboards, candlestick charts, and data tables
- Cross-platform TUI development
- Terminal event handling, focus management, and keyboard-first input processing
- Layout management and responsive design across terminal widths and heights

### When NOT to Use This Skill
- Graphical User Interfaces (desktop GUI frameworks like Qt, Tkinter, Electron)
- Web-based frontend applications (HTML/CSS/DOM, browser React)
- Mobile application development

---

## Project-Wide TUI Audit Workflow (`sktui`)

Whenever the user asks to **audit, check, verify, or review the project** using the `tui` skill (or invokes `tui` without a narrow single-file scope), execute the following **6-Phase Project-Wide Audit Workflow** across `src/sktui/` and `tests/` and return a structured report.

### Phase 1: Automated Test & Static Health Check
Run the test suite in the project's virtual environment to verify baseline behavior:
```bash
/home/man/Github/sktui/.venv/bin/pytest -q
```
If tests fail, inspect the failing tests in `tests/` (`test_ui.py`, `test_redesign_workspace.py`, `test_shortcuts_and_charts.py`, `test_themes.py`, `test_realtime_charts.py`, `test_performance_and_edge_cases.py`) before proceeding.

### Phase 2: Keyboard-First Navigation & Input Handling Audit
Inspect `src/sktui/app.py`, `src/sktui/screens/main.py`, `src/sktui/screens/login.py`, and `src/sktui/screens/modals.py`:
1. **Core Bindings Present & Conflict-Free**:
   - App-level: `ctrl+t` (`open_themes`).
   - MainScreen: `1`-`7` (pane/tab focus), `b`/`s` (Buy/Sell), `m` (Modify), `x`/`X` (Cancel/Cancel all), `K` (Panic Flatten), `f` (Focus mode), `r` (Refresh), `c` (Chart), `i` (Detail), `?` (Quote), `p` (Products/Market), `d` (Feed log), `a`/`delete` (Add/Remove symbol), `/` (Command bar focus), `escape` (Back/Escape context), `f1` (Help), `ctrl+l` (Logout), `q` (Quit).
2. **Input Capture Safety**:
   - Single-letter shortcuts (`b`, `s`, `c`, `q`, `1`-`7`, etc.) must **not** fire destructively while an `Input` widget (`#cmd-input`, modal inputs, login fields) has focus, or must be properly guarded by Textual focus priority.
   - `escape` in `MainScreen` (`action_escape_context`) and all `ModalScreen` subclasses (`modals.py`) must cleanly unfocus `#cmd-input`, exit focus mode, or dismiss the active modal (`self.dismiss(...)`).
3. **Slash Command Parity**:
   - Every command advertised in `SLASH_COMMANDS` (`src/sktui/config.py`) and `#cmd-input` placeholder must be handled in `MainScreen` command dispatch without raising unhandled exceptions.

### Phase 3: Responsive Layout & Terminal Breakpoint Audit
Inspect `src/sktui/app.py` (`HORIZONTAL_BREAKPOINTS`, `VERTICAL_BREAKPOINTS`), `src/sktui/styles.py`, and widget composition in `src/sktui/screens/` and `src/sktui/ui/widgets/`:
1. **Horizontal Breakpoints (`-xs` <90, `-sm` 90–119, `-md` 120–159, `-lg` 160–199, `-xl` 200+)**:
   - Verify `#left-pane`, `#center-pane`, `#right-pane`, and `#command-pane` widths do not overflow total terminal columns at 80x24 (`-xs`) or 100x30 (`-sm`).
   - Secondary chrome (`#sidebar`) must hide on `-xs` and `-sm`.
2. **Vertical Breakpoints (`-short` <30, `-medium` 30–44, `-tall` 45+)**:
   - On `-short` terminals (<30 rows), non-essential vertical chrome (`#indices-bar`, `#login-logo`, `#cmd-suggestions`, extra borders/margins) must collapse so the workspace and charts remain visible and usable.
3. **Dynamic Chart & Canvas Sizing**:
   - Check `src/sktui/chart.py`, `src/sktui/ui/widgets/chart_canvas.py`, `src/sktui/ui/widgets/chart_panel.py`, and `src/sktui/ui/widgets/symbol_focus.py` to ensure chart width/height adapt to container `size` / `content_size` on `Resize` events with safe minimum bounds (`max(1, ...)`).

### Phase 4: Differential Rendering & Performance Audit
Inspect `src/sktui/screens/main.py` and `src/sktui/ui/widgets/watchlist_table.py`:
1. **Differential Table Updates**:
   - Live tick updates must update cells in-place (`update_watch_row` / `DataTable.update_cell`) rather than clearing and rebuilding the entire `DataTable` on every WebSocket tick.
2. **Thread & Worker Safety**:
   - Blocking network I/O (Sharekhan REST calls, public IP lookup, WebSocket feed loops in `src/sktui/api/feed.py`) must run in background workers (`@work(thread=True)` or daemon threads) and marshal UI updates safely (`call_from_thread` or reactive state).
3. **Log & History Bounding**:
   - `RichLog` widgets (`#status-log`, `#feedlog`) must set `max_lines` (e.g., `max_lines=200`), and tick history buffers in `QuoteStore` must stay bounded to prevent memory leaks during market hours.

### Phase 5: Theme Reactivity & Visual Accessibility Audit
Inspect `src/sktui/themes.py`, `src/sktui/styles.py`, and Rich markup across `src/sktui/screens/` and `src/sktui/ui/widgets/`:
1. **Semantic CSS Variables**:
   - `src/sktui/styles.py` must use Textual semantic theme tokens (`$background`, `$surface`, `$panel`, `$primary`, `$secondary`, `$foreground`, `$text-muted`, `$border`, `$success`, `$warning`, `$error`) instead of hardcoded hex colors.
2. **Live Theme Switching (`on_theme_changed`)**:
   - When `SKApp.watch_theme` runs, `sync_palette_from_app` must update the active palette (`current_palette()`) and every mounted screen/widget (`refresh_watchlist_theme`, `SymbolFocusPanel`, `TopStatusBar`, `TradeRiskPanel`, modals) must re-render with the new palette without requiring an app restart.
3. **Visual Indicators & Accessibility**:
   - Positive/negative P&L and price changes must pair color (`C_GREEN` / `C_RED`) with explicit directional symbols (`+`, `-`, `▲`, `▼`) and clear focus borders so state is never communicated by color alone.

### Phase 6: Structured Audit Output Format
Present audit findings in a table ordered by severity (`CRITICAL`, `WARNING`, `SUGGESTION`), linking directly to the exact file and line range:

| Severity | Category | Location | Issue | Recommended Fix |
| :--- | :--- | :--- | :--- | :--- |
| `CRITICAL` / `WARNING` / `PASS` | Keyboard / Layout / Perf / Theme | `file.py#L10-L20` | Concise description | Actionable code fix |

---

## TUI Libraries

### Python (Primary for `sktui`)
- **Textual (`textual>=1.0`)**: Modern reactive TUI framework with CSS layout engine, screens, modals, `DataTable`, workers, and theme system
- **Rich**: Rich text formatting, `Text` objects, tables, and canvas/Braille rendering

### Go
- **Bubbletea**: Modern, idiomatic Go TUI framework (Elm architecture)
- **lipgloss**: Styling and colors
- **tview**: Rich interactive widgets and flexible layouts
- **tcell**: Low-level terminal manipulation

### Other Languages
- **ratatui** (Rust): Modern TUI library with crossterm backend
- **ink** (Node.js): React for CLIs

---

## Core TUI Patterns

### 1. Textual Reactive Screen & Differential Update Pattern (Python / `sktui`)

```python
from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import DataTable, Static


class TradingScreen(Screen):
    BINDINGS = [
        Binding("q", "app.quit", "Quit"),
        Binding("escape", "escape_context", "Back", show=False),
        Binding("r", "refresh_data", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(id="header-strip")
        yield DataTable(id="watch-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#watch-table", DataTable)
        table.add_columns("Symbol", "LTP", "Chg%")

    def on_resize(self, event: Resize) -> None:
        # Adapt layout or chart canvas dimensions safely
        cols = max(1, event.size.width // 40)
        self.set_class(event.size.width < 90, "-xs")
        self.set_class(event.size.height < 30, "-short")

    def update_tick_in_place(self, row_key: str, ltp: str, chg: str) -> None:
        # Differential update: update individual cells instead of rebuilding table
        table = self.query_one("#watch-table", DataTable)
        table.update_cell(row_key, "LTP", ltp, update_width=False)
        table.update_cell(row_key, "Chg%", chg, update_width=False)
```

### 2. Core TUI Pattern — Bubbletea (Go)

```go
type model struct {
    choices  []string
    cursor   int
    selected string
    width    int
    height   int
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        switch msg.Type {
        case tea.KeyCtrlC:
            return m, tea.Quit
        case tea.KeyUp:
            if m.cursor > 0 { m.cursor-- }
        case tea.KeyDown:
            if m.cursor < len(m.choices)-1 { m.cursor++ }
        case tea.KeyEnter:
            m.selected = m.choices[m.cursor]
            return m, tea.Quit
        }
    case tea.WindowSizeMsg:
        m.width = msg.Width
        m.height = msg.Height
    }
    return m, nil
}

func (m model) View() string {
    s := "Choose an option:\n\n"
    for i, choice := range m.choices {
        cursor := " "
        if m.cursor == i { cursor = ">" }
        s += fmt.Sprintf("%s %s\n", cursor, choice)
    }
    return s + "\nPress q to quit.\n"
}
```

## Input Handling

Key events to always handle:
- **Quit / Logout**: `q` / `Ctrl+C` (`app.quit`), `Ctrl+L` (`logout`)
- **Navigation**: `Up`/`Down` arrows, `Tab`/`Shift+Tab` focus cycling, `1`-`7` pane jumping
- **Confirm / Cancel**: `Enter` (confirm selection/submit), `Escape` (dismiss modal, blur command input, exit focus mode)
- **Resize**: Textual `Resize` event / `HORIZONTAL_BREAKPOINTS` & `VERTICAL_BREAKPOINTS` (or `tea.WindowSizeMsg` in Go)

## Responsive Layout

```python
# Python / Textual responsive layout helper
def adapt_layout(width: int, height: int) -> str:
    if width < 90 or height < 30:
        return "compact"      # -xs / -short: hide secondary chrome, stacked panels
    elif width < 120:
        return "standard"     # -sm: condensed sidebars
    return "institutional"    # -md / -lg / -xl: full 3-pane workstation

# Responsive grid column calculation
cols = max(1, term_width // 40)  # min 40 chars per column
```

## Best Practices

1. **Performance**: Use differential updates (`DataTable.update_cell`, partial widget refresh); minimize full screen/table redraws; bound `RichLog` lines and tick history arrays.
2. **Accessibility**: Full keyboard navigation for all interactions; visible `:focus` borders; pair colors with symbols (`+`/`-`/`▲`/`▼`); high-contrast dark and light themes.
3. **Cross-platform**: Test on Linux/macOS/Windows terminals; graceful layout fallbacks for small (`80x24`) terminals.
4. **UX**: Provide footer keybinding hints, slash-command autocomplete, confirmation modals for destructive actions (e.g. Cancel All `X`, Panic Flatten `K`), and live feed/status indicators.
