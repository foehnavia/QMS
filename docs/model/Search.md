---
part_of: MIS-QMS/docs/model
entity: Search
order: 100
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Search — by levels

> Search is organized by levels, from the most exact to the descriptive. One rule
> holds for all: the **unit of output is always the whole deviation**, even when the
> match was on a single dimension. Entry point: `_overview.md`.

## Levels

- **Level 1 — exact.** By the **(Item, dimension)** pair. If the dimension is
  canon-bound (in a CG), by the **canonical position (CG + g-index)** — which also
  matches other parts at the same constructive location (`CharacteristicGroup.md`). If
  the dimension is not in a CG, search runs on the (Item, dimension) pair. This is the
  level the **deviation card** shows automatically (`DeviationCard.md`).
- **Level 2 — descriptive.** By **zone** and **deviation type**
  (`reference/reference-data.md`). Used when there are no exact matches: finds similar
  cases by meaning (same part zone, same character of deviation — thread burr, angle,
  inner diameter, etc.). Works for all findings, including those not bound to the
  canon.
- **Deep search — query constructor.** Arbitrary queries over any field of all levels
  (Item ↔ finding ↔ deviation ↔ inspection), with any logic (AND/OR, ranges, nesting).
  **Read-only**; a separate stage (**1.5**) with high priority, right after the base
  skeleton (`staging.md`).

## Notes

- Reference lists **zone** / **deviation type** are populated by the operator (at
  entry) and cleaned by the administrator; a separate table.
- Zone and CG are distinct: zone is a soft search label; CG is the strict canon with
  geometry.

## Related

`DeviationCard.md` · `Finding.md` · `CharacteristicGroup.md` · `reference/reference-data.md` · `staging.md`
