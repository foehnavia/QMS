---
part_of: MIS-QMS/docs/model
entity: Deviation
order: 50
canon: true
rev: "1.03"
updated: 2026-09-07
---

# Deviation

> A recorded event: a non-conformance found on a batch of parts. A self-standing
> record with its own decision, quantity, date. Usually one deviation = one
> source-table row or one batch incident. Entry point: `_overview.md`.

## Attributes

- `item` (FK → `Item.md`)
- `revision` (FK → the Item's revision, `Item.md`) — which issue of the drawing this
  deviation was written against; see Revision below
- `WO` (string, `פק"ע`) — see WO below
- `machine` (optional)
- `quantity` — parts per this deviation (see Quantity levels)
- `date`
- `NCR` (string; may arrive later than the decision) — see NCR below
- `decision_date` (empty until there is a decision; written together with `decisionDev`)
- `decisionDev` (4-value dictionary — see Outcomes)
- `explanation` (free text, always)
- `attachment` (links to documents — photos, measurement reports — in an open
  network folder)

## Children

- findings `1..N` (`Finding.md`)
- inspections `0..N` (`Inspection.md`)

## Revision (QMS-017)

- The revision is chosen **first** — part, then revision, then findings. It is
  pre-filled with the part's **current** revision; moving it to a previous one is a
  separate, deliberate action, needed because parts of the previous issue keep arriving
  from the shop for two to three months after a change.
- The revision decides **which set of dimensions the form offers**, since dimensions
  belong to the part revision (`Characteristic.md`).
- **Changing the revision while entering recalculates nothing.** The local numbers were
  read off the inspection record and stay as typed; what changes is the revision they are
  read against. A wrong revision made the findings wrong; correcting it makes them right
  — no re-pointing, no clearing. (The hazard of silently re-interpreting what is already
  recorded belongs to **history**, not to a form still being filled.)
- A number that does not exist in the newly chosen revision falls under the standing
  rule — an unknown number is auto-created as a non-CG dimension — and is shown marked
  "not in this revision", so the operator sees what he is about to create.
- **Invariant:** a deviation and all its findings live in one revision.

## Integrity

**Integrity is at the deviation level:** it is not split by dimension (that would lose
the whole-part picture); the unit of search output is always the whole deviation
(`Search.md`).

## Outcomes — `decisionDev` dictionary

A live, non-procedural decision, set at the deviation level, not inherited, not
auto-derived.

| Code | Label | What happens to the parts | Closing document |
|---|---|---|---|
| `approved` | Approved — use as is | Proceed unchanged | **DS-QC.2-2** `אישור חריגה` — the main, most frequent one (`reference/output-document.md`) |
| `rejected` | Not approved — scrap | Scrapped | **none** |
| `sorting` | Sorting — 100 % screening | 100 % screened by a stated criterion (tolerance may be widened vs. the base); good ones proceed | Shared sorting/repair form, *sorting* mode |
| `repair` | Repair | Brought to an acceptable but **not fully conforming** state: the deviation remains but is sanctioned | Same form, *repair* mode |

- The term is **`repair`**, not `rework` (the part is not returned to full drawing
  conformance).
- **An inspection carries no verdict at all** (`Inspection.md` rev 1.03, QMS-025). It
  supplies information — a type, a written conclusion, a protocol — and nothing else. The
  rule "an inspection does not dictate the decision" stopped being a warning to observe and
  became structure: there is no field to break it with. *(History: rev 1.01 made
  `decisionInsp` three-valued to replace a binary one; rev 1.03 removed it, because the
  judgement it stood in for now has a proper home.)*
- **The judgement on one dimension lives on the finding** (`Finding.md` rev 1.01):
  `outcome` = `permitted` / `not permitted` / empty. It is the **input** to `decisionDev`,
  not a replacement: the finding says whether the dimension passed, the deviation says what
  happens to the batch.
- **Binding invariant — `approved — use as is` requires every finding to be `permitted`.**
  Checked when the deviation's decision is **saved**, not on the finding's form: any finding
  state other than `permitted` — *including empty* — closes that outcome. The other three
  (`rejected`, `sorting`, `repair`) require nothing: they are what the engineer picks
  precisely while sorting the matter out. Conversely, a finding cannot be changed to
  `not permitted` while its deviation stands `approved` — the edit is refused with an
  explanation, because silently voiding a decision that has gone into a document is worse
  than making the engineer withdraw it on purpose.
- **The sorting/repair forms are not modeled**: filled manually in ~95 % of cases;
  the sorting criterion is not stored.

> **Scope boundary.** Once a decision is entered, the further fate of the parts is
> **out of this base** (sorting → QC → stock or scrap; repair → check → possibly a
> repeat cycle). A repeat return is possible but sits at the **deviation-committee**
> level (depends on the scrap ratio in the WO) — not modeled here.

## WO (Work Order, `פק"ע`)

- The whole output produced under one production number on one machine.
- **An attribute, not an entity** — needed to search and group by WO; symmetric with
  NCR (a shared string over several deviations). Stored as one clean code `פק"ע`.
- Promotion trigger (to an entity): the first WO-level attribute (quantity/date/machine
  at WO level) or a hard WO-scope NCR.

## NCR

- The non-conformance report number kept by QA. A **string**, filled manually; opened
  against a WO but grouped by problem type: different problem types → different NCRs;
  same-type problems within a WO → one shared number.
- Several deviations simply carry the same string; no separate table is needed, and
  "all deviations by NCR" still works.

## explanation

- Free text, always present; feeds the `אישור חריגה` document **only on approval**;
  carries no decision (may reference an inspection in words). This is not the same as
  the form's procedural "inspection type" substitution — both coexist
  (`reference/output-document.md`).

## Quantity — three levels

1. **WO / `מנה`** — the whole output under that number on that machine. `פק"ע` and
   `מנה` are synonyms; the official name is `פק"ע` (Work Order). There is no separate
   "batch" level above the WO. *(Open item Q-07: the project glossary defines `מנה` as
   "a measured quantity, not the whole WO" — contradicts the user's usage, still to be
   reconciled.)*
2. **Deviation** — the number of parts per one deviation (`quantity`); parsed from the
   source table (`Import-Workflow.md`).
3. **Findings** — dimensions inside one deviation; **carry no quantity of their own**.

## Related

`Item.md` · `Finding.md` · `Inspection.md` · `DeviationCard.md` · `reference/output-document.md`
