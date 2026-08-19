---
part_of: MIS-QMS/docs/specs
spec: deviation-card
status: as-built
task: QMS-015
updated: 2026-08-17
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
| Deviation list → **"Карточка…"**, or double-click a row | the card | double-click **replaced** its S4 meaning (edit); "Открыть…" keeps the old path |
| Saving a **new** deviation | the card, by itself | canon: "opens as soon as a deviation is entered" |
| Card → **"Править…"** | `DeviationDialog` (S4) | the card re-reads itself on return |
| Card → **"Решение…"** | `DecisionDialog` (S4) | moved in **untouched**; the list keeps its own button |
| Card → finding row → **"Исследование…" / "Привязать к канону…"** | `InspectionDialog` / `MappingDialog.run(...)` | enabled by row selection |
| Precedent row → **"Открыть прецедент…"** or double-click | that deviation's card, on top | depth is not limited |

There is **no "Deviation card" navigation section**: a card is always about one deviation,
and an empty card has nothing to show. The "Поиск" section stays disabled and is marked S8.

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

**Точные (L1)** — two titled sections, each with its row count:

- **"Эта деталь, тот же размер"** — the same characteristic, i.e. the same physical
  dimension of the same part. The strongest match.
- **"Другие детали, та же позиция `gN`"** — other items bound to the **same g-position**.
  This is what the canon exists for: the same constructive location is comparable across
  parts whose local dimension numbers differ. The current item is excluded (it is already
  the first section), and items marked **code 99** never appear — code 99 is not a search
  key (`../model/CharacteristicGroup.md`).
  When the dimension has no mapping, the section is replaced by an explanation plus a
  **"Привязать к канону…"** button: binding is precisely what makes this search possible,
  so the dead end offers its own exit.

**Похожие (L2)** — descriptive search by **zone or deviation type**, with a "совпало по"
column (zone / type / both). The condition is deliberately `OR`: L2 earns its keep exactly
where an exact match is missing, and demanding both labels would switch it off. Rows
matching both rank first. A finding carrying neither label gets an explanation instead of a
table — the search rests on those two fields and nothing else.

**The card opens on L2 when L1 is empty** (both sections), so the operator does not stare at
two empty tables without noticing the second tab. This happens **at open only**: once the
card is up, switching findings never yanks the operator off the tab chosen by hand.

## 4. The unit of output is the whole deviation

`../model/Search.md` is explicit: even when the match was a single dimension, what comes
back is the deviation — number, date, item, WO, the matched dimension (with its `gN`),
sign and magnitude, decision, explanation, inspection count.

**L2 is collapsed by deviation**, keeping the strongest match: the query runs over findings,
so a deviation with two dimensions in one zone would otherwise appear twice and the
"похожих: N" counter would count findings instead of cases. L1a and L1b need no collapsing
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

## 7. Selection ownership (follow-up fix)

"Открыть прецедент…" and double-click must open the row the operator actually chose. Three
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
