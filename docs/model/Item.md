---
part_of: MIS-QMS/docs/model
entity: Item
order: 20
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Item

> The manufactured part (`item_number`). **Center of the model** — almost every
> grouping, sorting and query runs "from the part". Entry point: `_overview.md`.

## Definition

A manufactured product with its own catalog number (item number). Around it live its
**dimensions** (`Characteristic.md`), the **deviations** recorded against those
dimensions (`Deviation.md`), and the **canonical layer** (`CharacteristicGroup.md`)
that lets the same physical feature be compared across different parts.

## Attributes

- `item_number` — catalog / item number (key).
- Reference classifiers: `item_type`, `connection_type`, `size` — see
  `reference/reference-data.md`. Each of `connection_type` and `size` has a
  `General` default, so a part can be created even when the specifics are not yet
  relevant.
- **CG link is many-to-many** ("for growth"; in practice currently 0..1) — see
  `CharacteristicGroup.md`.

## Invariants

- An Item with **0 CG links is the mass case**.
- An Item never has **0 characteristics** once it exists: a part enters the base at
  its first deviation, and a deviation is always tied to dimensions.
- On Item creation only the **CG dimensions** are seeded; other dimensions are created
  automatically on the first deviation that references them (no form) — see
  `Characteristic.md`, `_overview.md` §6.

## Not carried over

- The two hidden Airtable rollup fields used for reports are **not** carried into this
  model.

## Related

`Characteristic.md` · `CharacteristicGroup.md` · `Deviation.md` · `reference/reference-data.md`
