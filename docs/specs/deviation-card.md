---
part_of: MIS-QMS/docs/specs
spec: deviation-card
status: as-built
task: QMS-015
amended_by: QMS-016, QMS-017, QMS-026
updated: 2026-09-09
amended_run: QMS-026 hand-run 2026-09-09
---

# Deviation card & precedent search L1/L2 — as-built spec (S5 / QMS-015)

> As-built: describes what sprint S5 delivered (worklog `0005-deviation-card-search.md`),
> reviewed and accepted 2026-08-17 (three review defects closed by a follow-up,
> `ee55428..5461e63`). Model canon: `../model/DeviationCard.md`, `../model/Search.md`.
> Schema: `../architecture.md` §5 (rev 0.2, **unchanged by S5** — the whole feature is
> queries). Entry form reused as-is: `deviation-entry.md`.

S5 is the key deliverable of stage 1: the card is what turns the database from an archive
into a working tool. The deep-search query constructor is stage 1.5 (S8) and is not
anticipated here.

## 1. Where it lives

| Entry point | Opens | Note |
|---|---|---|
| Deviation list → **"Card…"**, or double-click a row | the card | double-click **replaced** its S4 meaning (edit); "Open…" keeps the old path |
| Saving a **new** deviation | the card, by itself | canon: "opens as soon as a deviation is entered" |
| Card → **"Edit…"** | `DeviationDialog` (S4) | the card re-reads itself on return |
| Card → **"Decision…"** | `DecisionDialog` (S4) | moved in **untouched**; the list keeps its own button |
| Card → finding row → **"Inspection…" / "Bind to canon…"** | `InspectionDialog` / `MappingDialog.run(...)` | enabled by row selection |
| Precedent row → **"Open precedent…"** or double-click | that deviation's card, on top | depth is not limited |

There is **no "Deviation card" navigation section**: a card is always about one deviation,
and an empty card has nothing to show. The "Search" section stays disabled and is marked S8.

Editing an existing deviation does **not** pop the card — the operator already knows what
is in it.

## 2. Precedents are shown per selected finding

A deviation carries `1..N` findings, i.e. several dimensions. The card puts the findings
table on top; selecting a row redraws the whole precedent panel below it. One combined list
would mix unrelated dimensions of a five-dimension deviation into one heap; the engineer
works with one dimension at a time.

With no row selected the panel explains itself instead of showing empty tables, and the
finding actions are disabled (this also closes the S4 limit "buttons enabled by *the table
has rows*").

## 3. Two levels, two tabs

**Exact precedents (L1)** — two titled sections, each with its row count:

- **"Same item, same characteristic"** — the same characteristic, i.e. the same physical
  dimension of the same part. The strongest match.
- **"Other items, same position `gN`"** — other items bound to the **same g-position**.
  This is what the canon exists for: the same constructive location is comparable across
  parts whose local dimension numbers differ. The current item is excluded (it is already
  the first section), and items marked **code 99** never appear — code 99 is not a search
  key (`../model/CharacteristicGroup.md`).
  When the dimension has no mapping, the section shows **nothing** — see the amendment
  *The canon block goes quiet* at the end of this file (naryad `0038`). What stood here
  until then — an explanation plus a **"Bind to canon…"** button — was removed: it repeated
  what the `Canon` column and the `!` mark already say, and in the mass case (a non-CG
  dimension) it offered an action that does not exist.

**Descriptive precedents (L2) — REMOVED 2026-09-03 (QMS-016, worklog `0022`).**

The tab remains and carries an explanation instead of a list. What was here — an automatic
search by **zone OR deviation type** with a "matched on" column and a rank — was found wrong in
principle during the run: on a part **not bound to any group** the card showed a precedent from
an unrelated part, matched on one shared zone alone.

The rule, not the code, was at fault. A descriptive precedent is **not an automatic output**: it
is a search the engineer sets up from **several parameters at once**, for one case, without
saving the set. One attribute returns half the database. Details: `../model/Search.md`,
`OPEN_QUESTIONS_MIS-QMS` Q-16 (tied to Q-14).

**Exact precedents (L1) are untouched** — both sections, the "decided only" rule, ranking and
opening a precedent all stand as described above.

Kept in the code for the future filter machinery, named in the worklog: `_base_query`, `_row`,
`_fresh_first`, `exclude_characteristic`, the `match` field.


## 4. The unit of output is the whole deviation

`../model/Search.md` is explicit: even when the match was a single dimension, what comes
back is the deviation — number, date, item, WO, the matched dimension (with its `gN`),
sign and magnitude, decision, explanation, inspection count.

**L2 is collapsed by deviation**, keeping the strongest match: the query runs over findings,
so a deviation with two dimensions in one zone would otherwise appear twice and the
"descriptive: N" counter would count findings instead of cases. L1a and L1b need no collapsing
by construction — one dimension yields one finding per deviation, and one g-position holds
exactly one dimension per item ("1 balloon = 1 dimension").

**Only deviations with a decision are returned** (all levels). A precedent exists for the
sake of a ready decision and its wording; an undecided one has nothing to advise. The status
line says so out loud, so an empty result is not read as "never happened before". Known
consequence, accepted: a fresh identical case that has not reached its decision yet is not
visible as a repetition signal.

## 5. Query cost is bounded, and that is tested

Every list is one query regardless of row count; `canon_labels` answers the canon state of a
whole set in one query, `canon_labels_for_item` in two (it also covers "the dimension does
not exist yet", which has no characteristic to ask about). The S4 entry form was moved onto
the batch call, closing the `N+1` limit recorded in `deviation-entry.md` §8.

The tests count SQL statements (`conftest.count_queries`) on 2 and on 20 findings and demand
the same number. That counter earned its place immediately: it caught an `N+1` that lived
not in the searches but in **sorting findings** by `finding.characteristic.local_number` —
touching a relation inside a loop. Screens looked fine; only the counter saw it.

## 6. Bidi lesson refined (repo `CLAUDE.md` §9)

A composite cell — "sign · magnitude" — showed `0.05 −`. Isolating the sign and the number
**separately** is not enough: two isolates in a row remain two runs and are laid out
right-to-left inside an RTL cell. **One isolate around the assembled string** is the rule;
"print it through an isolate" is insufficient wording once a cell holds more than one token.

> **Refined again by QMS-016** (naryad 0007, mixed-cell stand). The S5 rule holds for what it
> was derived on — an **atomic** token with no strong character inside (`− 0.05`, `⌀ 3.75`).
> It does **not** carry over to a cell built of several independent tokens: one isolate around
> the whole string leaves the tokens themselves reordered. There the rule is **one isolate per
> token** (`ui.common.joined`). See `../decisions.md` and repo `CLAUDE.md` §9.

## 7. Selection ownership (follow-up fix)

"Open precedent…" and double-click must open the row the operator actually chose. Three
independent tables each keep their own current row, so preferring "the first table that has
a selection" opened a row from the first section while the operator was double-clicking in
the second. Double-click now carries its source table explicitly, and — because a button has
no source, and re-clicking an already selected row emits no selection signal — **selection
is physically kept in one table**: selecting in any of them clears the others. `fill()`
clears the selection too, so the skew does not survive a change of finding.

## 8. Mirror guard by content (Q-09, `tools/build_mirror.py`)

The vault mirror is now stamped with `source_hash` — a sha256 over the canon set — and
`--check` compares it against the canon as it is now, printing the file list, both hashes and
a verdict, writing nothing. `source_version` stays for humans; the guard no longer depends on
anyone remembering to bump `rev`.

Two properties the guard must have, both learned the hard way:

- **Line endings are normalised** (CRLF → LF) before hashing — otherwise a Windows checkout
  reports drift on byte-identical content;
- **files are hashed in relative-path string order**, not by comparing path objects: path
  comparison is case-insensitive on Windows and case-sensitive on POSIX, so the same canon
  produced two different hashes depending on the platform. That broke the one workflow the
  guard is for — Claude Code stamps on Windows, Cowork verifies from a Linux container. The
  hashing order is now printed by `--check` and is platform-independent by construction.

The generator writes **into the repo** (`build/mirror/`, git-ignored); carrying the artefact
into the vault is Cowork's step — Claude Code never writes to the vault (INFRA-013).

## 9. Related

`../model/DeviationCard.md` · `../model/Search.md` · `../model/CharacteristicGroup.md` ·
`deviation-entry.md` · `cg-editor-and-mapping.md` · `../decisions.md` ·
`../worklog/0005-deviation-card-search.md` · `../_INDEX.md` (mirror & sync)

---

## Amendment — revisions in the output (QMS-017, naryad `0024`, as-built 2026-09-06)

The precedent table gained a `Revision` column (position 4, right after `Item`) and two
marks. **Neither mark ever drops a row** — a match reached through a revision is marked,
never filtered out: filtering would hide exactly the precedent the card is opened for.

- **"Same item, another revision"** — the revision cell is set in bold and carries a
  tooltip naming the revision. Shown whenever the match's revision differs from the one
  the card is read from.
- **`!` on a non-canon dimension** — rendered as `! · 41` in the `Characteristic` cell,
  with a tooltip: the match rests on the local number alone, and the number belongs to the
  drawing. A canon-bound dimension carries no mark: it is resolved through the mapping of
  its own revision and is right by construction.
- `Revision` is **not** a numeric column: a designation is an identifier, not a magnitude —
  nothing to compare down the column, and the left edge keeps it under its heading.

**What the canon buys, measured on the run.** The direct path (L1a) searches by local
number across every revision of the item; when a number moved between revisions it finds
nothing, and that consequence is accepted (lazy re-linking is out of stage 1). The canon
path (L1b) resolves through the mapping of the finding's **own** revision, so it keeps
finding the precedent across the very re-issue that moved the number — verified on the
acceptance run, screenshot `19d-card-revision-marks.png`.

---

## Amendment — L1 sections cut by how the match was made (naryad `0025`, as-built)

The two exact sections used to be cut **by part** — "same item" and "*other* items, same
position". That was right while a part had one set of dimensions: same part plus same
g-position then implied the same local number, so the first section already covered it.
A revision breaks the implication, and a precedent could fall between the two sections —
the first missed it because the number had moved, the second discarded it because the
part was its own. Found by hand-running naryad `0024`, on `C1-10375A` / `g13` / `19 → 66`.

**As built now:**

- **By number** — `no. N, all revisions of this item`. Same part, same local number,
  every revision.
- **By canon** — `position gN — other items and other revisions`. The same canonical
  position across all parts **and all revisions, other revisions of this part included**.
  Excluded from it is only what the first section already showed: this part's dimensions
  carrying that same local number, in **any** of its revisions — a set, not one row,
  because the first section returns one dimension per revision. Exclude a single one and
  an unmoved number is listed twice.
- Headings state what the section returns. The old `Other items` would have started
  lying the moment the exclusion was lifted.

**The two marks differ by property, not by function** (revised after the acceptance of
naryad `0025`; `Search.md` v1.05):

| Property | Says | Where |
|---|---|---|
| **colour** (red) | there is nothing behind this number but the number — no canon to lean on | the dimension cell, non-CG only |
| **weight** (bold) | this row is another issue of the drawing | the revision cell, on **every** screen listing deviations |

They are read together, not against each other: a bold red row says "earlier issue, and no
canon either" — exactly the sum of its parts. Each property has one function in the code
(`ui.common.mark_unbound`, `ui.common.mark_other_revision`), and the revision mark is set
by the same call in the precedent sections and in a part's own deviation list, so one fact
cannot look different on two screens.

A canon-bound dimension from a previous revision therefore carries the row mark but **no**
`!` — the g-position finds it regardless of numbering. The whole cell is coloured rather
than the sign alone, because painting two runs inside one cell needs a delegate laying out
text by hand, and that is where this application's direction bugs lived (QMS-016).

*What was wrong before:* one function set both marks, so the revision column of the part's
deviation list came out red — colour borrowed for the other property's meaning — while the
same column in the precedent sections was merely bold.

The card header now carries `Revision` next to `Item`, read-only: a part number without a
revision does not say which drawing its local numbers are read against.


## Amendment — the panel, the summary and the empty sections (naryad `0035`, as-built)

Three parts of the card were changed after the QMS-026 hand-run. All three were found by
looking at the screen, not by a failing test.

### Inspections of the selected characteristic — the panel now reads

`Type` is measured against the **inspection-type reference**, not against the rows on
display: the column must hold the longest value the dictionary permits, and it must not
jump about as the operator moves between findings. The screen hands the set to the kit;
the kit never reaches for the database.

`Conclusion` is free text: it takes the remainder of the canvas, up to the reading ceiling
of 60 characters, and the full wording is a tooltip when it does not fit.

*What was wrong before:* both columns sat on their header floor — `F…` and `Not in …` —
with an empty field spanning the rest of the panel. The diagnosis "the table was never
moved to the kit" was wrong: it had been. The remainder simply never reached any screen
(see `CLAUDE.md` §9а.20, second case), and the type column had been declared with an empty
closed set.

### Inspections column — a summary, not a count

A bare number was useless: the panel below already lists the inspections of the selected
finding, and a count gives no reason to click.

| Inspections | The cell shows | The tooltip |
|---|---|---|
| none | `0` | none |
| one | type · conclusion, truncated by the column | the full wording |
| several | type of the first · `+N` | **every** inspection with its conclusion |

`+N` counts the ones **not** shown, matching `+N findings` in the finding chips — two
different conventions on one screen would read as a defect.

**The tooltip of the "several" case is shown always, truncated or not.** It carries what
the cell cannot: showing one inspection and staying silent about the rest would mislead.
This is a declared exception to the truncation rule (`design-system.md` §3), and the
mechanism for it is `kit.CONTENT_TOOLTIP_ROLE` — so that the next build order finds the
grounds here instead of "fixing" the tooltip away.

The column is sized from the reference as well: the widest type name plus `+N` always
fits. The conclusion of a single inspection may run past that and is truncated — which is
what the rule asks for.

### Empty L1 sections — the emptiness is hidden, not the section

- **Both groups empty** — one line, `No precedents yet`; neither group heading is drawn.
- **One group empty** — both headings stay. Otherwise it is not clear which of the two
  produced the result.
- The tab counter `Exact precedents (L1)` is untouched: it is the ordinary way to learn
  there are no precedents without expanding anything.

This refines, and does not reverse, naryad `0032`: "(0) is an answer, and a vanished group
reads as *the search did not run*". That holds for one empty group beside a full one. Two
zero headings in a row only take space and promise content that is not there.

### Explanation — a copy icon

Small, next to the field, shown **only when the field carries text**. Selecting with the
mouse worked before, but it required guessing that the text was selectable, and the
explanation is exactly what gets carried over into one's own deviation.

It copies the **stored** text, not what is on screen. `Copy explanation` at the foot of
the card is a different button on a different object — the explanation of the *selected
precedent* — and the two are not merged.


## Amendment — header, drawn height and two grids (naryad `0036`, as-built)

Found by the hand-run of 09.09 and by measurement; none of it was caught by a green test.

### The header is three columns

Nine requisites used to sit in two columns of five and four; they now sit in three of
three, read left to right in the order a deviation is entered: **what it is** (number,
item, revision) → **where it was made** (WO, machine, quantity) → **what records it**
(date, NCR, attachments). Measured: the header block drops from **338 px to 245** with an
explanation present, and from 258 to 232 without one. Those pixels go to the precedents,
which is what the card is opened for.

A label now sits on the **first line** of its value rather than on the middle of its row.

### The explanation takes the width the header has

It is the only header field whose value is prose, and it is a named exception
(`kit.prose_row`) to the rule that fields do not stretch. Measured before: 133 px of label
for 413 px of text at a 1600 px window, wrapping to three lines beside an empty half of the
header. After: the full width of the row, one line for a 128-character explanation at
`DIALOG_FULL`.

### Two declared grids

The precedent table has a full grid (**1462**) and a tight one (**1106**), chosen by the
canvas. At `DIALOG_FULL` the canvas is 1136 and the tight grid applies — `Characteristic`
and `Explanation` stay truncated with a tooltip, as naryad `0032` declared. Widen the card
and the full grid takes over: `Characteristic` stops truncating at 195, `Explanation` gets
440, and `Item` and `WO` hold the journal's real maxima (13 and 10 characters).

### No scrollbar where there is nothing to scroll

The findings table and the inspection panel used to carry a vertical scrollbar at two and
three rows. The declared height missed the frame by 2 px; it now includes it. The same
defect, and the same fix, applied to the expansion panel of the deviations list.

### The Inspections column reads the same on both screens

The card showed a summary and the entry form showed a bare count, though the column tuple
is shared and the findings panel is deliberately one component for both screens. Both now
show the summary, and the width is computed by one function from the inspection-type
reference.


## Amendment — the canon block goes quiet (naryad `0038`, as-built)

### §L1b, as it stands

**When the finding's dimension has no canonical mapping, the L1b area shows nothing.** Not a
heading, not a short line, not a compressed block — nothing.

What used to stand there — a 14 pt heading `Search by canonical position is unavailable`, an
explanation and a second `Mapping…` button — is gone. It said a third time what two other
things already said: the `Canon` column of the finding row carries `not bound`, and the `!`
mark sits on the dimension itself. It occupied **203 px of the 245 px** the L1b area has at
`DIALOG_FULL` — 83 % of the one region the card is opened for. **And in the common case it was
wrong on the merits:** the mass case is a non-CG dimension, which has no canon *by nature*;
offering to bind there offers an action that does not exist.

What remains is enough: the group row `By canon: this characteristic is not bound (0)` — with
that same explanation as its tooltip — and the counter on the `Exact precedents (L1)` tab. An
empty L1b is the **expected answer**, not a dead end needing a way out.

The action is not lost. The `Mapping…` button under the findings table stays, and it is now the
single place where binding is offered.

### What this spec deliberately does not describe yet

The model distinguishes **three** positions where the card now shows one. This is a **deferred
behaviour, not an interface decision** — and the difference matters, because the interface is
not free to choose here.

| Position | What it is | What the operator would do |
|---|---|---|
| **1.** The item revision has no characteristic group | there are no g-positions to bind to | assign a group to the item |
| **2.** There is a group; the dimension is not in it — non-CG, *the mass case* | there is no canon **by nature**; this is normal | nothing |
| **3.** The dimension belongs to the group but is unbound | exception R2: registered unlinked, mapped later | bind it |

**The canon of the model already carries this distinction** and is right to:
`CharacteristicGroup.md` §Mapping — "Optional: non-CG dimensions (the mass case) live without a
canon", "Code 99 is meaningful only where there is a group". **The schema does not carry it**,
and that is the whole of the reason. Established by measurement on data, naryad `0037`
(stop report, commit `77be5b7`):

- positions **2 and 3 are indistinguishable by any property of the dimension** — for both,
  `characteristic.mapping is None`, and `Characteristic` holds no other field about canon.
  `binding_state` answers about a **g-position of the group**, not about a dimension of an item;
- both tables that tie an item to canon — `mapping` and `item_position_absent` — are keyed by
  **g-position**. There is no record saying *this dimension is not covered by canon*;
- position **1** is likewise not directly recorded: `groups_of` derives the group **from the
  mappings themselves**, so "a group was assigned but nothing is bound yet" is indistinguishable
  from "there is no group". A header line `Characteristic group: not assigned` would therefore
  lie in that state, and is deliberately not added.

**Two facts are missing, and both are schema, not screen:**

1. an explicit link from an item revision to its characteristic group;
2. a record that a dimension has been reviewed and has no canon — the counterpart of code 99,
   but on the dimension.

Until they are materialised, showing one behaviour for all three is the honest option: the
alternative would be to guess, and a guess here is a promise of an action that may not exist.
