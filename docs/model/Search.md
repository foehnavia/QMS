---
part_of: MIS-QMS/docs/model
entity: Search
order: 100
canon: true
rev: "1.02"
updated: 2026-09-06
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
  - at this stage the set is **not saved**; saving filter sets and re-running them belongs
    with the query constructor of stage **1.5**;
  - it is a consumer of the **filter machinery** of the reference screen, not a second
    tab of automatic output.
  **Base parameter set** (closed 2026-09-06, Q-16 — base, not final; it will be adjusted in
  use): from the part — part type, connection type, dimension class; from the finding — zone,
  deviation type, direction, magnitude range; framing — period, presence of inspections.
  **Guard: at least two parameters.** The result is shown **on the list screen**, through the
  same filter machinery — no separate screen; entry is a button from the card that pre-fills
  the filters from the current finding. **Resolved deviations only by default, with a
  toggle.** Built together with part 2 of Q-14 (reference-screen mechanics), after S6.
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
