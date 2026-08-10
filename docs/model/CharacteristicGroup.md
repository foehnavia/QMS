---
part_of: MIS-QMS/docs/model
entity: CharacteristicGroup
order: 40
canon: true
rev: "1.00"
updated: 2026-08-10
---

# CharacteristicGroup (CG) / g-position — the canonical layer · and Mapping

> The reference layer that lets the same physical feature be compared across
> different parts. Includes **Mapping** (Q-06 decision: mapping lives here, not in a
> separate file — it is one paragraph tightly coupled to the g-position). Entry
> point: `_overview.md`.

## CharacteristicGroup / g-position

- A small **static reference** (~20–30 groups system-wide). Normally
  admin-maintained; a missing group **may also be created on the fly** when a part is
  created (see `docs/decisions.md`, R3).
- A CG has a name (e.g. `Implant_Con_375_C1`) and a set of canonical positions
  `g1…gN`.
- **Nominal and tolerance are baked into the CG schema** (from the drawing); the
  moderator does not enter them.
- No versioning in stage 1. A second-level CG (linking constructively similar parts)
  is out of scope for now — it only imposes keeping the Item↔CG link many-to-many
  (`Item.md`).

### State and g-positions

- **State is not a separate axis** (see `Characteristic.md`): stages of one dimension
  are split into **separate g-positions** (invariant: a state change always changes
  both the local number and the value).
- There is no composite `(characteristic, state)` key; a mapping points to **one**
  g-position. Unmapped (non-CG) state dimensions stay two separate dimensions.

## Mapping

- Links **(item, local#) → one canonical g-position** (single-field FK).
- Built **manually and incrementally**, assigned by a human. **Created early — before
  the deviation is registered** (buttons "Create mapping / link" sit in the deviation
  entry form, next to "Create Item"). See `_overview.md` §5–6.
- **Optional**: non-CG dimensions (the mass case) live without a canon.
- Code **99** = "the part does not have this position" (a technical stub; a `g:99`
  pair explicitly records "the position was considered, it is absent"). Not a search
  key.

> **Canon note (R2).** Retroactive mapping is treated as a data-loss risk and is
> **not** the default (this reverses session 06's "lazy resolve"; see
> `docs/decisions.md`, R2). The only exception is an **urgent WO**: the dimension may
> be registered unlinked and mapped later.

## Distinction from Zone

Zone and CG are distinct: **zone** is a soft search label (see `Finding.md`,
`reference/reference-data.md`); **CG** is the strict canon with geometry.

## Related

`Item.md` · `Characteristic.md` · `Finding.md` · `Search.md` · `reference/reference-data.md`
