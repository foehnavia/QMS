---
part_of: MIS-QMS/docs/model
entity: Characteristic
order: 30
canon: true
rev: "1.01"
updated: 2026-09-06
---

# Characteristic (dimension)

> One controlled dimension of a specific part **in a specific revision of its
> drawing**. An **attribute of the Item revision, not a standalone entity**, held in a
> separate table (many-to-one normalization). Entry point: `_overview.md`.

## Identity

- Key: **(item, revision, local_number)** — the number is unique only within one
  revision of one part (QMS-017; before that the key was `(item, local_number)`).
- A "dimension 12" apart from its part does not exist, and apart from its revision it
  does not exist either: a re-issued drawing may give number 12 to a different feature.
- Linking dimensions of **different parts** happens **only through the canon
  (mapping)**, never by number — see `CharacteristicGroup.md`. Linking dimensions of
  **different revisions of the same part** is a separate matter and is not built in
  stage 1 (`Item.md`, Revision).

## Lifecycle

- On revision creation only the **CG dimensions** are seeded, into that revision.
- A new revision is created by cloning the previous one: its dimensions arrive
  pre-filled and the operator edits only what changed (`Item.md`).
- Other dimensions are created **automatically on the first deviation** that
  references them (no form) — inside the revision recorded on that deviation.
- A **finding references a characteristic** by FK on the row `(item, revision, local#)`;
  it does not store a bare number, and it does not store a revision of its own — the
  revision comes with the characteristic. The canon is reached through this
  characteristic's mapping (`CharacteristicGroup.md`).

## Attributes

- `item_revision` (FK), `local_number`.
- Optional **`state-depending dimension`** attribute (see below): a **reference to
  another characteristic of the same part** — a nullable self-FK, empty by default,
  **not** a copied local number. It stays **inside one revision**: a self-FK across
  revisions would tie together two drawings, which is a different relation entirely.
  **Dormant**: not used in ordinary search, reserved for future special queries.

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
key is unique only inside one revision of the part anyway. The attribute is
**dormant**. Typically ≤ 5 state dimensions per part (usually 3).

> **Canon note (R1).** At session 06 such a linking attribute was considered and
> rejected for stage 1. In rev 1.00 it is reintroduced as a dormant field — a
> deliberate reversal (see `docs/decisions.md`, R1). Its physical shape was ratified
> with schema rev 0.1 in S1 (`docs/decisions.md`, ratification 1): **self-FK, not a
> number**; this text is the prose synchronized to that ratification (S5 / QMS-015).

## Related

`Item.md` · `CharacteristicGroup.md` · `Finding.md`
