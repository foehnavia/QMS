---
part_of: MIS-QMS/docs/model
entity: Characteristic
order: 30
canon: true
rev: "1.00"
updated: 2026-08-17
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
- Optional **`state-depending dimension`** attribute (see below): a **reference to
  another characteristic of the same part** — a nullable self-FK, empty by default,
  **not** a copied local number. **Dormant**: not used in ordinary search, reserved
  for future special queries.

## Part states (e.g. before / after electropolishing)

There is **no separate "state" axis** in the model: a change of state always brings a
new dimension number *and* a new value — this is reflected directly in the drawing.

*Example.* Drill XXX has a production dimension — leg diameter, № `AA`, value 2.0 mm.
After electropolishing the number becomes `AB` and the value 1.9 mm. Branch:

- **Dimension belongs to a CG** → each state receives its own g-position (its own
  g-index).
- **Dimension is not in a CG** → the states remain two separate dimensions under
  their own numbers.

To link such dimensions, the **`state-depending dimension`** attribute is provided:
a nullable **self-reference to the other characteristic row of the same part**
(`characteristic.state_depending`, empty by default). It holds a real foreign key, not
a copy of the other dimension's number: a copied number would be a second spelling of
an identity the table already owns, free to drift once either row is renamed — and the
key `(item, local_number)` is unique only inside the part anyway. The attribute is
**dormant**. Typically ≤ 5 state dimensions per part (usually 3).

> **Canon note (R1).** At session 06 such a linking attribute was considered and
> rejected for stage 1. In rev 1.00 it is reintroduced as a dormant field — a
> deliberate reversal (see `docs/decisions.md`, R1). Its physical shape was ratified
> with schema rev 0.1 in S1 (`docs/decisions.md`, ratification 1): **self-FK, not a
> number**; this text is the prose synchronized to that ratification (S5 / QMS-015).

## Related

`Item.md` · `CharacteristicGroup.md` · `Finding.md`
