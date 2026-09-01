---
part_of: MIS-QMS/docs/design
doc: design-system
status: ratified
task: QMS-016
branch: run/qms-016
updated: 2026-08-31
---

# MIS-QMS design system — tokens and rules

> Single source for every visual value in the application. The Qt stylesheet is generated
> from this file, not from screenshots. Ratified 2026-08-31 (QMS-016, design session);
> the visual reference is the design canvas `MIS-QMS Deviations UI` (artboard
> **Design system**), this file is its machine-readable half.
>
> Scope: the whole application, not one screen. A screen spec (`docs/specs/`) may not
> introduce a colour, a height or a radius that is not here — it extends this file first.

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
reason not to import a webfont. Fallback stack: `Segoe UI, Selawik, system-ui, sans-serif`.

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

**Tabular figures are mandatory** on every numeric run — dates, quantities, counters,
magnitudes, business numbers. Without them `0.05` and `0.11` occupy different widths and the
eye stops comparing down a column. In Qt: `QFont.setStyleStrategy` plus the `tnum` feature,
applied on the application font, not per widget.

## 3. Metrics

| Group | Values |
|---|---|
| Zone heights | top bar 48 · section header 64 · tab strip 44 · toolbar 52 · table header 34 · **table row 40** · footer 36 |
| Controls | primary button 32 · toolbar button 30 · nav item 32 · pill 22 · row action 24 |
| Icons | 16 (navigation, toolbar) · 13 (in-row, inside pills) · 34 (empty state) |
| Radius | button/input 5 · card/panel 7 · row action 4 · pill 11 (full) |
| Strokes | border 1 px `n-200` · inner rule 1 px `n-100` · selection bar 2 px `blue-600` inset left |
| Spacing | screen padding 20 · sidebar padding 14/10 · cell padding 10 · control gap 8 · nav icon gap 9 · pill icon gap 6 |
| Sidebar | 240 wide (48 collapsed) |
| Focus | 1 px `blue-600` border + 3 px `blue-halo` — **never a size change**, so nothing shifts by a pixel on focus |

Row height 40 is a deliberate compromise: Airtable's short row is 32, but Hebrew ascenders and
descenders need the extra 8 px to avoid clipping at 13 px type.

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

## 9. Related

`../specs/deviations-list.md` (screen spec) · `../worklog/0008-ui-deviations-airtable.md`
(build order) · `../architecture.md` §3.1 (English/LTR ratification) · `../decisions.md` ·
repo `CLAUDE.md` §9 (bidi and test conventions) · design canvas **MIS-QMS Deviations UI**
