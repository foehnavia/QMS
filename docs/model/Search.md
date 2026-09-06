---
part_of: MIS-QMS/docs/model
entity: Search
order: 100
canon: true
rev: "1.01"
updated: 2026-09-03
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
- **Level 2 — descriptive. Not an automatic output — a search the engineer sets up**
  (revised 2026-09-03, QMS-016; supersedes the S5 ratification of an automatic
  "zone OR type" list). The purpose stands: find parts that **cannot be linked by a
  characteristic group** yet are close enough that an earlier decision means something.
  The mechanics change:
  - the engineer composes a set of parameters — **several at once**, never one. A single
    attribute (zone alone, type alone) returns half the database, which is noise, not a
    precedent;
  - the set is composed **for one case**, each time anew;
  - at this stage the set is **not saved**; saving filter sets and re-running them is a
    later, separate piece of work;
  - it is a consumer of the **filter machinery** of the reference screen, not a second
    tab of automatic output.
  Open: which attributes make up the set, where the result is shown, when saving arrives
  (`OPEN_QUESTIONS_MIS-QMS` Q-16, tied to Q-14).
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
