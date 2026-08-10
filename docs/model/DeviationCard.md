---
part_of: MIS-QMS/docs/model
entity: DeviationCard
order: 80
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Deviation card — the key deliverable

> The working screen of a single deviation. Hosts the system's **key deliverable**:
> an automatic overview of past deviations on the same dimension (or the same
> canonical position). Entry point: `_overview.md`.
>
> Made explicit as the key deliverable in rev 1.00 (`docs/decisions.md`).

## Behaviour

Opens as soon as a deviation is entered. It automatically shows an **overview of past
deviations**:

- all deviations with a matching **(Item, dimension)** pair, and
- for dimensions bound to the canon, by the matching **canonical position
  (CG + g-index)** (`CharacteristicGroup.md`).

A **query constructor** for second-level search is available here as well
(`Search.md`).

## Why it matters

This is what turns the base from an archive into a working tool: the engineer sees
whether the deviation occurred before, what was decided and how it was justified —
decisions become uniform and precedent-based (see process Step 6 in `_overview.md`).

## Related

`Deviation.md` · `Search.md` · `CharacteristicGroup.md` · `Inspection.md`
