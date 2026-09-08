---
part_of: MIS-QMS/docs/design
doc: design-system
status: ratified
task: QMS-016
branch: run/qms-016
updated: 2026-09-07
revision: 1.13
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
> the target machine, C-4 by replacing the side navigation with the ribbon, and adds §10 —
> the component list the code library `src/ui/kit/` implements one-to-one.
>
> **Revision 1.2 (2026-09-01, review of `0011`).** Two leftovers of the side navigation
> removed from the tables (R-2), and §8 gains the **compact** empty state: two full ones
> stacked in a card is the wrong variant of the component, not a shortage of space (O-6).
>
> **Revision 1.3 (2026-09-01, review of `0012`).** Six chrome heights taken from the design
> canvas — the vertical budget at 1280 × 760 buys one more row of data on every screen (M-1).
> Icons stay as they are here. §0 settles what `Dimension`, `Local number` and `g-position`
> each name; §4 gains the rule that decides between radio buttons and a dropdown.
>
> **Only this file carries a `rev`.** The canvas is dated, not numbered: two independent
> counters are what produced the argument "canvas 1.4 against canon 1.2", where the numbers
> were never comparable in the first place. A showcase is not versioned alongside its source.

## 0. What governs

Three decisions from QMS-016 stand above every value below:

1. **Interface is English**, labels taken from canon words (Item, Characteristic group,
   g-position, Deviation, Finding, Inspection, Mapping).

   Three of those words were confused with each other often enough to be settled here:

   | Word | What it names |
   |---|---|
   | **Dimension** | the entity itself — a dimension of an item (`Characteristic`) |
   | **Local number** | what that dimension is called **on this item** |
   | **g-position** | what the same dimension is called **in the canon of its group** |

   A finding has no dimension of its own: it **refers** to one by the pair (item, local
   number). The only real distinction is the canonical position against the local number;
   everything else is a dimension.

   Which of the three goes on a label follows the convention these screens already use: the
   column `Item` holds an `item_number`, the column `Deviation` holds a `dev_number` — **a
   column is named after the entity and holds its identifier**. So the findings table says
   `Dimension` (`Dim.` where the grid is tight), and `Local number` stays where the number
   itself is what gets assigned or edited: the mapping dialog and the item positions table.
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
| `n-50` | `#F7F9FB` | table header, footer, hover row, filter panel |
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
It is the quiet ground under a working surface — never navigation: navigation is the
ribbon below, and it is dark.

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
| Section caption | 10.5 | 700 | letter-spacing +0.07em, `n-400` — a group of rows inside a screen |

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
| Zone heights | **navigation ribbon 44** · screen header 48 · tab strip 34 · toolbar 52 · table header 30 · **table row 40** · status bar 26 |
| Controls | primary button 28 · input 26 · toolbar button 30 · nav item 32 · pill 22 · row action 24 |
| Icons | 16 (navigation, toolbar) · 13 (in-row, inside pills) · 34 (empty state) |
| Radius | button/input 5 · card/panel 7 · row action 4 · pill 11 (full) |
| Strokes | border 1 px `n-200` · inner rule 1 px `n-100` · selection bar 2 px `blue-600` inset left |
| Spacing | screen padding 20 · ribbon padding 16/0 · cell padding 10 · control gap 8 · nav icon gap 9 · pill icon gap 6 |
| Window | minimum 1280 × 760 |
| Dialog heights | short 320 · medium 620 · tall 820 · **card 960** |
| Table width | at most 90 % of the window, **and never narrower than 1216** — 1728 at 1920, **1216** at 1280 |
| Focus | 1 px `blue-600` border + 3 px `blue-halo` — **never a size change**, so nothing shifts by a pixel on focus |

Row height 40 is a deliberate compromise: Airtable's short row is 32, but Hebrew ascenders and
descenders need the extra 8 px to avoid clipping at 13 px type. **One state, one number**
(C-3): 40 is the row everywhere.

**The table-width floor of 1216 was added 2026-09-07 (QMS-018), and it is a revision of empty
space, not of the 90 % rule's intent.** At 1920 the rule donates 192 px of ground, which reads
as air around a working surface. At the 1280 minimum the same percentage donates 128 px while
the columns starve — and columns are what the operator came for. The floor keeps a 32 px margin
each side at the minimum window and returns 64 px to the grid; the 90 % rule keeps governing
every wider window.

**A declared column width is not a drawn column width** (QMS-018, naryad `0028`). Qt applies its
own section minimum, the stylesheet subtracts cell padding, and the drawn text area comes out
6–8 px narrower than the number set. So a width is **valid only once measured on the native
platform** with the real font: a sum of declared numbers can balance perfectly while a value on
screen is clipped. Every width in a screen grid is a measured value or it is a guess.

**The gap has a size and it is computed, not assumed** (measured in the doving of `0028`):
**27 px of a column never prints** — 1 px grid line, 20 px of stylesheet cell padding, 6 px of
Qt's own margins. Hence the shape of every width in a screen grid:

> **declared width = what the text needs + 27**

`kit.FIT_LABEL` predates this and adds only the cell padding, so a column sized by its header is
**7 px short on every screen** — `Revision` was clipping its own heading unnoticed. The fix is
one place, not one screen: task **QMS-022**.

**Measure against the widest value the domain permits, not the widest one in the database
today.** `Qty` measures at 47 px against real quantities and is set to **56**, because `9999` —
the marker the import writes for a sampled batch — is a legitimate value the column must hold.
`Findings` is sized by the longest deviation type in the dictionary, not by the longest one a
demo database happens to contain. A column fitted to today's data is a column that clips the
day real data arrives.

**Dialog heights belong here, not to `tokens.py` alone** (added 2026-09-07, QMS-018). A dialog
takes the **smallest of the four that holds its content without clipping** — the height is a
choice among declared values, never a number invented at the screen. `card 960` was added when
the deviation card gained the inspections section: with four stacked sections at `tall 820` the
precedent list — the deliverable the whole screen exists for — collapsed to a scrollbar. Both
`tall` and `card` are measured values, not estimates, and both defects were found by a
screenshot rather than by a green test (§9а.8 of the repo `CLAUDE.md`): a layout that clips is
invisible to a test that only asserts the widget exists.

**The one exception to the 40 px row is the deviations list, and it is the exception the rule
was written around** (QMS-018, 2026-09-07). There the row carries the finding chips themselves, so it
grows with them: **40 / 66 / 82** for one / two / three-or-more findings. The composition,
corrected 2026-09-07 after naryad `0028` (the earlier prose did not close arithmetically):

| Findings | Height | Made of |
|---|---|---|
| 1 | **40** | the ordinary row minimum — one chip fits inside it |
| 2 | **66** | `40 + (chip 22 + gap 4)` |
| 3 or more | **82** | `66 + 16` — the **`+N findings` line**, not a third chip |

There is no third chip at any count: two are shown and the rest become one text line.
Inside an expanded record the finding sub-row is **28 / 43 / 58**
by the number of inspections listed. Everywhere else the row stays 40, and no other screen
inherits these numbers — the mechanics of the reference screen are not tiled onto the others
(naryad `0010` §3а, ratified by the user 2026-09-01).

**Expansion follows the object, not the screen.** Wherever a table row *is a deviation* — the
deviations list, the precedent table inside a card — the row expands the same way, with the same
panel, the same sub-row heights and the same three levels: deviation → its findings → the
inspections at each finding. This is not the previous paragraph's exception but its complement:
what must not be tiled is a screen's *mechanics*; what must not be forked is an *object's*
presentation. An engineer who learned to read an expanded deviation in the list has learned to
read it everywhere, and a second panel with its own columns would make him learn it twice
(naryad `0031`).

**Every number here is a logical pixel** at 100 % Windows scaling — not a point. Declared as
points they come out a third larger (13 pt ≈ 17 px), which is how the chrome grew until five
ribbon sections stopped fitting the 1280 minimum (measured, review of `0012`).

**The chrome is deliberately tight** (M-1, review of `0012`): screen header 48, status bar 26,
primary button 28, input 26, tab strip 34, table header 30. Together they give back about
40 px at the 760 minimum — **one more row of data on every screen**. For a tool whose work is
reading tables, a row is worth more than air. These six replaced 64 / 36 / 32 / 32 / 44 / 34;
the ribbon is untouched at 44 (B-5), and so is the 40 px row.

**The ribbon is always 44** (В-5). Height does not follow width: squeezing at 1280 is
horizontal, and what leaves the ribbon is section captions, counters and the right-hand
status string — never pixels of height. Counted, not tasted: full chrome at the 760 minimum
is 44 + 48 + 52 + 34 + 30 + 26 = **234**, leaving **13.15** rows of 40; a 36 px ribbon would buy one
fifth of a row and cost a second vertical state that every screen, screenshot and test would
have to carry. If vertical space ever runs short, the 48 px section header is what gives.
> The old chrome summed to 274 and left 12.15 rows: the tightening bought **exactly one row**,
> which is the whole basis on which it was ratified — the figure now checks out, whereas this
> paragraph carried the pre-tightening arithmetic until QMS-016 caught it.

## 4. Controls

- **One primary action per screen.** Everything acting on a selected row is secondary — the
  screen's job is reading, not acting.
- Secondary button: `white` background, 1 px `n-250` border, `n-700` text.
- Danger button: `white` background, 1 px `#F0CFCE` border, `#99312F` text. Colour lives on
  the outline, not on a filled red block — a filled destructive button reads as the primary
  action of the screen.
- Disabled: `n-50` background, `n-250` border, `n-450` text. Never a lower opacity — opacity
  on top of a light surface makes the text unreadable rather than obviously disabled.

**Radio buttons or a dropdown — the rule, not the taste.** A choice of **five or fewer mutually
exclusive values that have to be compared before choosing** is radio buttons; a dropdown hides
the alternatives and costs a click to see them. It matters most where the operator chooses by
**reading the wording** rather than recalling it: the deviation outcome (four of them, each a
sentence) and the inspection result (two). A dropdown stays for open-ended lists — reference
values, items, groups — where the count is unbounded and the choice is by name, not by
comparison.

**Every control kind that appears in the application has its sub-style described here, and a
control kind appearing for the first time is verified by a screenshot.** Qt draws an undeclared
sub-style with the platform default, and against this palette that can come out as *nothing at
all*: the first checkbox in the application, `No protocol`, rendered as a bare caption with no
box to click — the stylesheet described `QRadioButton::indicator` (from naryad `0019`) but never
`QCheckBox::indicator`. The defect had existed since naryad `0011` and simply waited for a
checkbox to exist. Two consequences: a new control kind is a **theme** change, not a screen
change, and it is signed off by a picture — no test asserts that a widget is visible in the
sense a person means.

**The primary button of a form names the action it performs, not the screen it was opened
from.** A record being created — `Add <object>`; an existing one being edited — `Save`. The
label follows the form's **mode**, not the call site: one form serving both modes must tell the
truth about itself in each. Introduced 2026-09-07 (QMS-025, doving of `0030`): the finding form
said `Add finding` while editing a saved finding, and by then that button recorded a judgement.
A label that is right on one form and lying on the next is worse than one uniformly wrong —
the operator stops reading labels at all.

**A choice that carries consequence has no default.** Neither the outcome of a deviation nor
the result of an inspection is preselected: a preselected radio is an answer the operator never
gave, and both of these end up in a document.

**Required fields are marked with `*` in the caption, and the mark is live.** It reflects
whether the field is required **right now**, not a static property of the form: `Conclusion *:`
gains its asterisk when `No protocol` is set and loses it when the flag is cleared. A static
mark on every mandatory field would put an asterisk almost everywhere and stop being read; a
live one answers the only question the operator has at that moment — what does this form want
from me before it will save. Introduced 2026-09-07 (QMS-024).

## 5. Icons

Inline stroke SVG, 1.7 px stroke on a 24 grid, round caps and joins, single style throughout.
**No emoji, no dingbat glyphs anywhere in the interface** — they do not recolour, do not scale
with the type ramp, and render differently on every machine.

**The grid is not the size.** An icon is drawn on a 24 grid and placed at 16 (§3); those are two
different numbers, and collapsing them is what put "16 grid, 1.5 stroke" in the canvas. At the
same size on screen a 1.5 stroke drawn on 16 reads thinner and worse, so the values above stand
— this is the one place where revision 1.3 did **not** follow the canvas (M-1).

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

**The right-alignment rule is about a magnitude in a column of its own.** In a **composite
cell** — nominal and tolerance joined as two isolated tokens — alignment follows the token the
eye actually compares. That is the nominal, and it sits at the leading edge of the cell, so the
cell aligns **left**: aligning right would line up the tail of the tolerance instead, which
nobody compares. Applies to `Canon geometry` in the mapping dialog (QMS-016, В-6). The letter of
the rule and its reason part company here — the reason wins, and this note records why, so the
next reader does not "fix" it back.

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
- **A cell is single-line by default; a column may be declared two-line in its screen grid.**
  The default protects the vertical rhythm — and two 15 px lines still sit inside the 40 px row,
  so a declared two-line column costs no height at all. `Explanation` on the deviations list is
  two-line, as the design canvas drew it from the start ("свёрнута — две строки, высота строки
  40 px"); at any width in that screen's budget the real justification does not fit on one line,
  so a single-line rule there would mean truncating the main text of a precedent. Two-line is a
  **per-column declaration**, never a screen-wide or application-wide default: a column that
  wraps without being declared is a defect, not a feature.

### One level, one header

**Two tables with identical columns standing in the same region are one table with group rows.**
Two headers over the same kind of row do not divide the data — they divide the *reading*: the
operator stops comparing rows and starts comparing tables. Where the grouping carries meaning
(the precedent area distinguishes "same dimension" from "same canon position"), the meaning goes
into a full-width **group row** inside the single table, which is cheaper than a header and says
more, because it can name the group and count it.

**Inside an expanded record, the sub-table's header is a label strip, not a table header.** Same
labels, subordinate weight: no header fill, no rule above, `12/500` in `n-500`. It is telling the
reader what the columns of the detail are, not announcing a new table. The header itself stays —
seven columns of numbers without names are a riddle, and compactness bought by removing names is
paid for in misreading (naryad `0032`).

### Only one region of a dialog stretches

**Every region of a dialog is sized by its content; exactly one is declared the stretching one,
and it takes everything left over.** A fixed floor on a region that holds one row — a 150 px
minimum for a 70 px table — is not a safety margin, it is a hundred pixels taken from whatever
the dialog was opened for.

The stretching region gets a floor stated in **what must be visible**, not in pixels: the card's
precedent area must show two precedent rows and one fully expanded panel. If the window cannot
give that, the dialog grows; the comparison is not what shrinks.

An inline section with nothing in it collapses to **one line** (§8, compact variant) — a box with
a sentence in the middle of it spends a section's worth of height to say that there is nothing
here.

## 8. Empty states

Every empty state answers three things: **what is empty**, **why**, and **one way out**. An
empty table that says nothing is how an operator concludes "there were no precedents" from a
screen that was merely filtered.

Two variants, and the choice between them is not about space:

| Variant | Shape | Where |
|---|---|---|
| **Full** | icon 34 `n-300` · title 14/650 · body 12/`n-500` · one button | the empty state **of a screen or a tab** — the whole surface is empty, and the button is the way out |

The **modal message** takes the same icon size, **34** — no new number is introduced. Both
cases explain a situation rather than label an element, and that is what the size answers to.
| **Compact** | one line, 12/`n-500`, no icon and no button | a **section inside** a screen that has siblings — the way out belongs to the surface around it |

The rule is the unit, not the pixel count: a section that is one of several in a view states
its emptiness in a line, because the reader is scanning the view, not the section. Two full
empty states stacked in one window is the wrong variant of the component — it was chosen
because both sections were treated as whole surfaces, which they are not.

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
| `slice_tab` | a tab strip 34 px | counts on tabs ignore filters — they answer "how much is there" |
| `decision_badge` | the pill of §1 | undecided is the only outlined one; the word always accompanies the colour |
| `hint` | a line of explanation under a control | says why, not what |
| `empty_state` | §8, full and **compact** | full for a screen or a tab, compact for a section that has siblings |
| `error_box` | the modal of a `DomainError` | the domain writes the text; the UI does not rephrase it |
| `status_bar` | the 26 px status bar | carries counts and the database path |
| `ribbon` | the 44 px navigation strip | always 44; captions leave before pixels do |
| `picker` | a modal choice out of a list | one substring filter row, **hidden at 12 values or fewer**; it narrows the choice, never the list underneath |
| `finding_chip` | the **22 px** chip carrying one finding inside a deviation row (same height as `pill` in §3 Controls) | `Dim. N` · signed value · deviation type, plus a 13 px flask glyph **only** when that finding has inspections; the glyph is a presence mark, never a verdict |
| `expansion_panel` | the full-width block under an expanded deviation row | its own 24 px header and its own column grid — it is not a continuation of the table above; it never takes selection and never receives arrow-key focus, because the unit of action stays the deviation |

## 11. Related

`../specs/deviations-list.md` (screen spec) · `../worklog/0008-ui-deviations-airtable.md`
(build order) · `../worklog/0011-ui-kit-and-screens.md` (the library and the screens) ·
`../architecture.md` §3.1 (English/LTR ratification) · `../decisions.md` ·
repo `CLAUDE.md` §9 (bidi and test conventions) · design canvas **MIS-QMS Deviations UI**
