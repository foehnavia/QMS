---
part_of: MIS-QMS/docs/model
entity: Deviation
order: 50
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Deviation

> A recorded event: a non-conformance found on a batch of parts. A self-standing
> record with its own decision, quantity, date. Usually one deviation = one
> source-table row or one batch incident. Entry point: `_overview.md`.

## Attributes

- `item` (FK → `Item.md`)
- `WO` (string, `פק"ע`) — see WO below
- `machine` (optional)
- `quantity` — parts per this deviation (see Quantity levels)
- `date`
- `NCR` (string; may arrive later than the decision) — see NCR below
- `decision_date` (default = system time)
- `decisionDev` (4-value dictionary — see Outcomes)
- `explanation` (free text, always)
- `attachment` (links to documents — photos, measurement reports — in an open
  network folder)

## Children

- findings `1..N` (`Finding.md`)
- inspections `0..N` (`Inspection.md`)

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
- **`decisionInsp` stays binary** (`approved` / `not approved`) and is independent of
  `decisionDev` (`Inspection.md`): an inspection answers "can this deviation be
  accepted", not "what to do with the batch".
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
