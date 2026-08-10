---
part_of: MIS-QMS/docs/model
entity: Characteristic
order: 30
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Characteristic (dimension)

> One controlled dimension of a specific part. An **attribute of Item, not a
> standalone entity**, held in a separate table (many-to-one normalization).
> Entry point: `_overview.md`.

## Identity

- Key: **(item, local_number)**; the number is unique **only within the part**.
- A "dimension 12" apart from its part does not exist. Linking dimensions of
  different parts happens **only through the canon (mapping)**, never by number —
  see `CharacteristicGroup.md`.

## Lifecycle

- On Item creation only the **CG dimensions** are seeded.
- Other dimensions are created **automatically on the first deviation** that
  references them (no form).
- A **finding references a characteristic** by FK on the row `(item, local#)`; it
  does not store a bare number. The canon is reached through this characteristic's
  mapping (`CharacteristicGroup.md`).

## Attributes

- `item` (FK), `local_number`.
- Optional **`state-depending dimension`** attribute (see below): default `none`,
  may hold the linked dimension's local number; **dormant** (not used in ordinary
  search; reserved for future special queries).

## Part states (e.g. before / after electropolishing)

There is **no separate "state" axis** in the model: a change of state always brings a
new dimension number *and* a new value — this is reflected directly in the drawing.

*Example.* Drill XXX has a production dimension — leg diameter, № `AA`, value 2.0 mm.
After electropolishing the number becomes `AB` and the value 1.9 mm. Branch:

- **Dimension belongs to a CG** → each state receives its own g-position (its own
  g-index).
- **Dimension is not in a CG** → the states remain two separate dimensions under
  their own numbers.

To link such dimensions, the **`state-depending dimension`** attribute is provided
(empty by default, may hold the number of the linked dimension). It is **dormant**.
Typically ≤ 5 state dimensions per part (usually 3).

> **Canon note (R1).** At session 06 such a linking attribute was considered and
> rejected for stage 1. In rev 1.00 it is reintroduced as a dormant field — a
> deliberate reversal (see `docs/decisions.md`, R1).

## Related

`Item.md` · `CharacteristicGroup.md` · `Finding.md`
