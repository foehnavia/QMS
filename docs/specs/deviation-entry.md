---
part_of: MIS-QMS/docs/specs
spec: deviation-entry
status: as-built
task: QMS-014
amended_by: QMS-015, QMS-016
updated: 2026-08-19
---

# Deviation entry — findings, decision, inspection — as-built spec (S4 / QMS-014)

> As-built: describes what sprint S4 delivered (worklog `0004-deviation-findings-inspection.md`),
> reviewed and accepted 2026-08-17 (one follow-up fix, `e0a5665..3cc0105`). Model canon:
> `../model/Deviation.md`, `../model/Finding.md`, `../model/Inspection.md`. Schema:
> `../architecture.md` §5 (rev 0.2, **unchanged by S4**). Mapping dialog reused as-is:
> `cg-editor-and-mapping.md`.

After S4 the database is filled **by hand end to end**. The deviation card and precedent
search are S5; the Excel import is S6. Neither is even partially anticipated here.

## 1. Where it lives

| Entry point | Opens | Note |
|---|---|---|
| Section **"Deviations"** (main window) | deviation list | active nav item since S4 |
| List → **"Add deviation…" / "Open…"** | deviation form | registration and edit, same form |
| List → **"Card…"** or double-click | deviation card | added in S5; double-click **used to** open the form for editing — that path is now the "Open…" button (`deviation-card.md` §1) |
| List → **"Decision…"** | decision dialog | step 8, **separate action**; since S5 the same dialog is also reachable from the card |
| Deviation form → finding row → **"Inspection…"** | inspection dialog | inspection belongs to a finding |
| Deviation form → **"Bind to canon…"** | `MappingDialog.run(...)` | the R2 "early buttons" |

The "Search" section stays disabled — a standalone search screen is the stage-1.5 query
constructor (S8). The card never became a section: it is always about one deviation
(`deviation-card.md` §1).

## 2. Process order is enforced by the UI shape

Canon puts registration at step 3 and the decision at step 8, after precedents (step 6) and
inspections (step 7) have been studied. So the registration form **has no outcome field at
all**: the deviation is born with an empty decision, and the outcome is entered by a separate
button from the list. `DecisionDialog` knows nothing about the deviation section — in S5 it
moves into the card unchanged.

## 3. Deviation form

- Header: item (+ **"Create item…"**, the existing `ItemDialog`), WO, machine, quantity,
  date, NCR, attachment.
- **Attachment** is a multi-line field, one link per line, plus "Choose file…" which inserts a
  path. Files are **not copied** into the database — the blob exception covers CG drawings only
  (`../architecture.md` §4).
- **Item is chosen at registration and frozen afterwards.** The dimensions of the findings
  belong to that item; moving the deviation would orphan them. Enforced by the form; the domain
  simply does not accept an item on update.
- Findings table with **"Add finding…" · "Edit…" · "Remove" · "Bind to canon…" ·
  "Inspection…"**; columns: local number, canon, direction, value, point, zone, deviation
  type, inspection count.
- **Save is blocked until an item and at least one finding exist**, and the status line says
  which of the two is missing. A deviation without a dimension is invisible to precedent search,
  i.e. useless (canon `1..N`).
- **Deviation + all its findings are written in one transaction** on "Save".

### 3.1 Write order inside the transaction (fix of the review)

Findings are **written first, removed second**, and the keep-set is collected *during* the
write. Deleting first makes a full replacement of all findings hit the domain guard "at least
one must remain" — the new ones are not in the database yet. That path is not exotic: the local
number of a saved finding is read-only, so "add the right one, drop the wrong one" is the only
way to fix a typo in a dimension number. Computing the keep-set *before* the write is the
symmetric trap: a new row still has `finding_id = None`, so the delete loop would sweep away
the findings just created. Removal still goes through `remove_finding`, so both guards hold.

## 4. Finding dialog

- The dialog **writes nothing**: it hands a filled row back to the deviation form, which saves
  everything at once. There is no `Finding(...)` anywhere in `src/ui/**` — creation goes through
  `make_finding` only, enforced by an AST check over the UI package.
- **Direction is mandatory and has no default** — the operator picks the sign deliberately, from
  the max/min wording of the source. Qualitative checks (`GO`, pin) live in the comment.
- A dimension the item does not have yet is created **by the domain at save time**, without a
  form (`../model/_overview.md` §6).
- **The local number of a saved finding is read-only**: another dimension is another finding.
- Two findings on the same dimension inside one deviation are refused — that is one finding.
- Canon state of the dimension is shown live, in three reachable values:

| Shown | Meaning |
|---|---|
| `g5` | the dimension is mapped to that g-position |
| "not bound" | the dimension exists on the item, no mapping yet |
| "not created yet" | new finding, the characteristic does not exist yet |

> **"Absent from item (99)" is not among them, by construction.** Code 99 marks a g-position the
> item *lacks*; a finding is always about a dimension the item *has* — that is what deviated.
> The naryad's three-value wording was wrong; this table is the ratified set.

## 5. Decision dialog (step 8)

- Four outcomes with human labels (`../model/Deviation.md`): approved / rejected / sorting /
  repair. Nothing is preselected while the deviation is undecided — a preselected list would
  suggest an outcome by mere ordering.
- **`approved` without an explanation is refused** — the text goes into `אישור חריגה`
  (DS-QC.2-2). The rule is shown as a hint *before* the click, not only in the error.
- Changing the decision **rewrites `decision_date`**: the date belongs to the decision in force,
  not to the first one.
- **NCR semantics:** the number comes from QA and may arrive after the decision; it is entered
  both at registration and here. Therefore in `set_decision` **`ncr=None` means "leave as is"**,
  not "erase" — passing an empty string erases it explicitly. This is deliberately asymmetric
  with `decision_date=None`, which means "now".
- The verdict of an inspection **never** constrains the outcome (see §6).

## 6. Inspection

- Created **as an action on a selected finding**, `0..N` per deviation; the deviation is derived
  from the finding, never passed separately. There is no "Inspections" section: an inspection
  targets a concrete finding, and picking it out of a global list would only add a way to miss.
- A **non-empty protocol is mandatory**: an inspection is recorded only when a reusable written
  analysis exists. All the "science" lives in the protocol, not in fields.
- `decision_insp` is **independent** of `decision_dev`. An approved inspection under a rejected
  deviation is a valid combination, and no check ties them.
- **Cannot be created on an unsaved finding** — it references a `finding` row, and findings are
  written on "Save". The button is disabled with the reason in the status line.
- **Mirror lookup** `inspections_for(item, characteristic)` returns every inspection for the
  pair (Item, dimension). The pair is **derived** through the finding; no columns were added to
  the schema. Both halves are filtered explicitly — a local number is unique only within an item.

## 7. Invariants enforced in the domain (not the form)

- finding ∈ the item of its deviation (`ensure_finding_target`);
- a deviation keeps **at least one** finding — the last one is not removable, delete the
  deviation instead;
- a finding carrying inspections is not removable — the message states how many;
- deleting a deviation takes its findings and inspections with it; the item's **dimensions
  survive** (a dimension exists independently of findings and of the canon);
- `approved` requires a non-empty explanation;
- `update_*` functions **replace their fields wholly** — no defaults, so an omitted argument
  cannot masquerade as "leave this alone" (the one documented exception is `ncr`, §5).

## 8. Known limits (recorded, not defects)

- `decision_date` is NOT NULL with a `now()` default, so a freshly registered deviation carries
  a decision date while having no decision. "Undecided" is read from `decision_dev`, so
  behaviour is correct, but an export would mislead. Changing it is a migration → flagged on S7.
- ~~Canon state is queried per row (`N+1`)~~ — **closed in S5**: the form uses the batch
  `precedents.canon_labels_for_item`, and a query counter holds the number fixed
  (`deviation-card.md` §5).
- Zone and deviation type cannot be created from the finding dialog, unlike Item and CG. Their
  reference lists are curated by an administrator (`../model/reference/reference-data.md`);
  quick-add would breed synonym duplicates.
- ~~The inspection buttons are enabled by "the table has rows" rather than "a row is
  selected"~~ — **closed in S5**, in both the form and the card.

## 9. Related

`../model/Deviation.md` · `../model/Finding.md` · `../model/Inspection.md` ·
`../model/_overview.md` §6–§7 · `../architecture.md` §4–§5 · `../decisions.md` ·
`cg-editor-and-mapping.md` · `../worklog/0004-deviation-findings-inspection.md`
