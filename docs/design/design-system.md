---
part_of: MIS-QMS/docs/design
doc: design-system
status: ratified
task: QMS-016
branch: run/qms-016
updated: 2026-09-01
revision: 1.1
---

# MIS-QMS design system — tokens and rules

> Single source for every visual value in the application. The Qt stylesheet is generated
> from this file, not from screenshots. Ratified 2026-08-31 (QMS-016, design session);
> the visual reference is the design canvas `MIS-QMS Deviations UI` (artboard
> **Design system**), this file is its machine-readable half.
>
> Scope: the whole application, not one screen. A screen spec (`docs/specs/`) may not
> introduce a colour, a height or a radius that is not here — it extends this file first.
>
> **Revision 1.1 (2026-09-01, build order `0011`).** Closes C-1 and C-2 by measurement on
> the target machine, C-4 by replacing the sidebar with the navigation ribbon, and adds §10
> — the component list the code library `src/ui/kit/` implements one-to-one.

## 0. What governs

Three decisions from QMS-016 stand above every value below:

1. **Interface is English**, labels taken from canon words (Item, Characteristic group,
   g-position, Deviation, Finding, Inspection, Mapping).
2. **The window chassis is LTR** — navigation, buttons, dialog frames.
3. **Direction is a property of the paragraph** (a table cell, a list row), never of the
   window. See §6.

The application **does not inherit the system theme.** A light palette is set explicitly at
start-up, so a workstation switched to Windows dark mode does not repaint the screens into
something nobody designed. One theme only — a second doubles the surface on which contrast
and bidi defects hide.

## 1. Colour

### Blue — the single accent

| Token | Value | Used for |
|---|---|---|
| `blue-50` | `#EFF5FE` | selected row background, active chip background |
| `blue-100` | `#E4EDFC` | active navigation item background |
| `blue-500` | `#3B7BE8` | focus ring |
| `blue-600` | `#2563D9` | primary button, identifiers, selection bar, active borders |
| `blue-700` | `#1B4FBF` | pressed primary, selected-row identifier |
| `blue-halo` | `#DCE7FB` | 3 px focus halo around a focused control |

### Neutral — cool-toned

| Token | Value | Used for |
|---|---|---|
| `white` | `#FFFFFF` | screen background, table background |
| `n-50` | `#F7F9FB` | sidebar, table header, footer, hover row, filter panel |
| `n-100` | `#EFF2F5` | inner rules, muted counter background |
| `n-200` | `#E3E7EC` | borders |
| `n-250` | `#DCE0E6` | control borders |
| `n-300` | `#C7CDD5` | dashed pill border, disabled glyph |
| `n-400` | `#8B94A1` | muted text, section captions |
| `n-450` | `#B4BCC7` | row numbers, placeholder text |
| `n-500` | `#6C7683` | secondary text, column headers |
| `n-600` | `#4A525D` | body text in notes |
| `n-700` | `#3C444E` | table body text |
| `n-900` | `#1B2027` | primary text |

`n-50` is the ground of the table header, the footer, the hover row and the filter panel.
It is **not** a sidebar colour any more — there is no sidebar (see the ribbon below).

### Ribbon — the navigation strip, and the only dark surface

The application has no side navigation: the deviations table is wide, and a horizontal
scroll in it costs more than a vertical one. Navigation is a 44 px ribbon across the top,
dark so that the working surface below stays the only white plane on the screen.

| Token | Value | Used for |
|---|---|---|
| `ribbon` | `#16324F` | ribbon background |
| `ribbon-text` | `#FFFFFF` | brand mark, active section |
| `ribbon-muted` | `#9FB3CC` | inactive section, right-hand status string |
| `ribbon-active` | `#1E4470` | background of the active section |
| `ribbon-border` | `#0F2438` | 1 px line under the ribbon |

### Decision — four outcomes plus the open state

| State | Background | Text | Dot | Shape |
|---|---|---|---|---|
| Undecided | none | `#6C7683` | `#A9B1BC` ring | **1 px dashed `#C7CDD5`** |
| Approved — use as is | `#E4F4EA` | `#1E6B3F` | `#2E9155` | filled |
| Rejected | `#FCE8E8` | `#99312F` | `#C7433F` | filled |
| Sorting | `#FDF0DC` | `#8A5A15` | `#C58A2A` | filled |
| Repair | `#EFE7FA` | `#5C3D96` | `#8763C7` | filled |

Two rules that are not decoration:

- **Undecided is the only outlined pill.** The four outcomes are settled facts; "no decision
  yet" is an open item, and an unfilled shape reads as unfinished when scanning the column.
- **Colour never carries meaning alone.** Every pill also carries its word, so the column
  survives a monochrome print and a colour-blind reader.

## 2. Type

One family: **Segoe UI** — present on the target machine, and its Hebrew coverage is the
reason not to import a webfont. Fallback stack: **`"Segoe UI", "Arial", "Tahoma"`**.

The stack is what `QFontDatabase` reports on the target machine, not what reads well in a
list (C-1, measured under build order `0011`): all three are installed and all three declare
Hebrew. Four candidates were dropped for stated reasons — `Selawik` is not installed;
`Segoe UI Historic` is installed but carries no Hebrew, so it is useless as the fallback it
was proposed to be; `system-ui` and `sans-serif` are CSS concepts and mean nothing to Qt.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Screen title | 18 | 650 | letter-spacing −0.01em |
| Section subtitle | 11.5 | 400 | `n-400` |
| Table body | 13 | 400 | `n-700` |
| Identifier (DEV-…, WO) | 13 | 600 | `blue-600`, tabular figures |
| Column header | 11 | 700 | letter-spacing +0.03em, `n-500`, upper case |
| Pill label | 11.5 | 600 | |
| Status / footer | 11.5 | 400 | `n-500` |
| Sidebar group caption | 10.5 | 700 | letter-spacing +0.07em, `n-400` |

**Tabular figures are the reason right alignment means anything** — without equal digit
widths `0.05` and `0.11` occupy different widths and the eye stops comparing down a column.

**Nothing has to be switched on to get them** (C-2, measured under build order `0011`).
Every family in the stack already advances all ten digits identically at every size
measured — 9, 11, 13, 24 and 48 pt — so `QFont.setFeature(QFont.Tag("tnum"), 1)` changes no
width, and the fallback mechanism once proposed for numeric columns solves a problem that
does not exist. Neither is in this canon. What remains is the constraint itself: a family
that did **not** advance digits equally could not be adopted into the stack, because the
right-aligned columns of §6 rest on this.

## 3. Metrics

| Group | Values |
|---|---|
| Zone heights | **navigation ribbon 44** · section header 64 · tab strip 44 · toolbar 52 · table header 34 · **table row 40** · footer 36 |
| Controls | primary button 32 · toolbar button 30 · nav item 32 · pill 22 · row action 24 |
| Icons | 16 (navigation, toolbar) · 13 (in-row, inside pills) · 34 (empty state) |
| Radius | button/input 5 · card/panel 7 · row action 4 · pill 11 (full) |
| Strokes | border 1 px `n-200` · inner rule 1 px `n-100` · selection bar 2 px `blue-600` inset left |
| Spacing | screen padding 20 · ribbon padding 16/0 · cell padding 10 · control gap 8 · nav icon gap 9 · pill icon gap 6 |
| Window | minimum 1280 × 760 |
| Focus | 1 px `blue-600` border + 3 px `blue-halo` — **never a size change**, so nothing shifts by a pixel on focus |

Row height 40 is a deliberate compromise: Airtable's short row is 32, but Hebrew ascenders and
descenders need the extra 8 px to avoid clipping at 13 px type. **One state, one number**
(C-3): 40 is the row everywhere, and the three-level 40 / 66 / 82 of the reference canvas
belongs to row expansion, which is not built.

**The ribbon is always 44** (В-5). Height does not follow width: squeezing at 1280 is
horizontal, and what leaves the ribbon is section captions, counters and the right-hand
status string — never pixels of height. Counted, not tasted: full chrome at the 760 minimum
is 44 + 64 + 52 + 44 + 34 + 36 = 274, leaving 12.15 rows of 40; a 36 px ribbon would buy one
fifth of a row and cost a second vertical state that every screen, screenshot and test would
have to carry. If vertical space ever runs short, the 64 px section header is what gives.

## 4. Controls

- **One primary action per screen.** Everything acting on a selected row is secondary — the
  screen's job is reading, not acting.
- Secondary button: `white` background, 1 px `n-250` border, `n-700` text.
- Danger button: `white` background, 1 px `#F0CFCE` border, `#99312F` text. Colour lives on
  the outline, not on a filled red block — a filled destructive button reads as the primary
  action of the screen.
- Disabled: `n-50` background, `n-250` border, `n-450` text. Never a lower opacity — opacity
  on top of a light surface makes the text unreadable rather than obviously disabled.

## 5. Icons

Inline stroke SVG, 1.7 px stroke on a 24 grid, round caps and joins, single style throughout.
**No emoji, no dingbat glyphs anywhere in the interface** — they do not recolour, do not scale
with the type ramp, and render differently on every machine.

## 6. Direction and alignment — two separate decisions

**Direction** is resolved per paragraph:

| Content | Base | How |
|---|---|---|
| Latin identifier (`C1-08375A`) | LTR | first strong character |
| Hebrew value (`אזור הברגה`) | RTL | first strong character |
| Mixed (Hebrew + term + number) | RTL, each token isolated | `joined()` — one isolate per token |
| Date, quantity, counters | LTR | **declared by column**, never resolved |

Dates and pure numbers carry no strong character at all, which is why `19.08.2026` used to
render as `2026.08.19`. Numeric columns are **declared in a list**, not guessed.

**Alignment** is a different question from direction:

- **Right** — magnitudes the eye compares down a column: `Qty`, `Value`, `Nominal`,
  `Tolerance +/−`, `Sign · value`.
- **Left** — dates, counters (`Findings`, `Inspections`, `Characteristics`, `Positions`),
  identifiers and numbers. Nothing to compare, and the left edge keeps them under their header.

> **Qt trap, already paid for once:** `QStyle.visualAlignment` is applied on top of
> `displayAlignment`, so under an RTL base a request for "right" becomes "left". A test that
> asserts the *requested* alignment passes while the screen is wrong. Assert what is drawn, or
> assert on a screenshot.

## 7. Table

- Row is the unit of selection; a cell never takes focus.
- Row states: default `white` · hover `n-50` · selected `blue-50` + 2 px `blue-600` inset bar.
- The selected row's identifier darkens to `blue-700` — on `blue-50` the `blue-600` identifier
  loses too much contrast.
- Column widths are **fixed**, except the two that stretch (see the screen spec). A column that
  resizes under the cursor is a column the operator re-finds on every visit.
- No editing in place, no row colouring by decision, no grouping. The pill carries the state;
  a coloured row would compete with the selection.

## 8. Empty states

Every empty state answers three things: **what is empty**, **why**, and **one way out**. An
empty table that says nothing is how an operator concludes "there were no precedents" from a
screen that was merely filtered. Icon 34 px `n-300`, title 14/650, body 12/`n-500`, one button.

## 9. What a stylesheet cannot say

Qt Style Sheets cover colour, border, radius, padding and font size. Three things below are
in this canon anyway, and each is set in widget code instead:

- **OpenType features** — `tnum` and friends are unreachable from QSS; only
  `QFont.setFeature()` sets them. Kept here as a note, not as a requirement: §2 measured that
  the stack needs none.
- **Text direction** — `layoutDirection`, the per-cell delegate and the isolates of §6 are
  code, and deliberately so: direction follows the value, and a stylesheet never sees values.
- **The palette a widget draws itself with** — `QPalette` still feeds what QSS does not
  reach (the calendar popup of a `QDateEdit`, the tooltip ground). The application sets an
  explicit light palette at start-up (§0); it never inherits the system one.

## 10. Components — the library, one to one

`src/ui/kit/` is this section in code, and it is the **only** place a colour, a font size, a
padding, a radius or a height is written down. A screen that spells out a number of its own
has left the design system, and the guard in `tests/test_ui_kit.py` fails on it.

| Component | What it is | Rules that are not decoration |
|---|---|---|
| `tokens` | every value of §1–§3 as a flat constant | names match the token names above |
| `theme` | the stylesheet built from tokens, the font stack, the explicit light palette | applied once to the application, never per widget |
| `data_table` | the table of §7 | fixed columns, row is the unit of selection, direction per cell |
| `field_row` | caption + control, one row of a form | caption stands beside its own field, never above a stretched one |
| `dialog` | the frame: title, body, button row | chassis LTR; one primary action |
| `primary` / `secondary` / `danger` buttons | §4 | one primary per screen; danger is an outline, never a filled red block |
| `slice_tab` | a tab strip 44 px | counts on tabs ignore filters — they answer "how much is there" |
| `decision_badge` | the pill of §1 | undecided is the only outlined one; the word always accompanies the colour |
| `hint` | a line of explanation under a control | says why, not what |
| `empty_state` | §8 | answers what is empty, why, and one way out |
| `error_box` | the modal of a `DomainError` | the domain writes the text; the UI does not rephrase it |
| `status_bar` | the 36 px footer | carries counts and the database path |
| `ribbon` | the 44 px navigation strip | always 44; captions leave before pixels do |
| `picker` | a modal choice out of a list | one substring filter row, **hidden at 12 values or fewer**; it narrows the choice, never the list underneath |

## 11. Related

`../specs/deviations-list.md` (screen spec) · `../worklog/0008-ui-deviations-airtable.md`
(build order) · `../worklog/0011-ui-kit-and-screens.md` (the library and the screens) ·
`../architecture.md` §3.1 (English/LTR ratification) · `../decisions.md` ·
repo `CLAUDE.md` §9 (bidi and test conventions) · design canvas **MIS-QMS Deviations UI**
