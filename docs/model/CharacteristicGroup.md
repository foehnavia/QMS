---
part_of: MIS-QMS/docs/model
entity: CharacteristicGroup
order: 40
canon: true
rev: "1.00"
updated: 2026-09-01
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
- **The drawing itself belongs to the CG** (stored inside the database; PNG/JPEG,
  ≤5 MB) and each g-position carries **balloon coordinates** `x`/`y`, normalised to
  0..1 of the image. The visual editor draws balloons `g1…gN` on top of the drawing;
  a CG **without** a drawing still works — balloons fall back to a grid. Rationale
  and the size threshold: `architecture.md` §4–§5 (QMS-013).
- A position's **`g_index` is its identity** — mappings of every part point at it, so
  it is not renumbered in place: add a new position and drop the old one instead.
- **An index is issued once and never reused.** A new position takes `max(current) + 1`;
  the index is not typed by hand, and a gap left by a deleted position is never filled.
  The reason is not referential integrity — the surrogate `g_position_id` keeps that —
  but the **shared vocabulary of drawing and database**: `g5` is written on the drawing,
  in the inspection record and in the operator's note. The tool exists to compare across
  time, and a label that silently changes meaning between revisions breaks exactly that,
  with nothing in the system to catch it. Accepted residue: deleting the *last* position
  lets the next one take the same index; a strict "never" needs a monotonic counter on the
  group (a schema revision). The residue is narrow — only a position that was never bound
  to anything can be deleted at all (`decisions.md`, QMS-016).
- **A range of g-positions is an input gesture, not a stored rule.** "Mark g1…g24" marks
  every position existing in that interval **at the moment of the action** and immediately
  materialises into a list of mappings. No interval is stored, nothing is recomputed on
  read: after the rule above, gaps are legal, and "g1—g24" would otherwise either change
  meaning retroactively or falsely claim that 1…24 all exist (`decisions.md`, QMS-016).
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
- **One balloon = one local dimension = one link**, enforced both ways: a g-position
  takes a single dimension of a given part, and a dimension is linked to a single
  g-position. Re-linking a taken dimension is never silent — clear it first.
- Code **99** = "the part does not have this position" (a technical stub; a `g:99`
  pair explicitly records "the position was considered, it is absent"). Not a search
  key. **Physically it is the pair (item, g-position)** in its own table
  (`item_position_absent`), not a flag on the mapping row: the flag could not record
  *which* position was missing (`decisions.md`, S1 №6 revised — rev 0.2, QMS-013).
  Search by `(cg, g_index)` never returns such a part — there is nothing to join.

> **Canon note (R2).** Retroactive mapping is treated as a data-loss risk and is
> **not** the default (this reverses session 06's "lazy resolve"; see
> `docs/decisions.md`, R2). The only exception is an **urgent WO**: the dimension may
> be registered unlinked and mapped later.

## Distinction from Zone

Zone and CG are distinct: **zone** is a soft search label (see `Finding.md`,
`reference/reference-data.md`); **CG** is the strict canon with geometry.

## Related

`Item.md` · `Characteristic.md` · `Finding.md` · `Search.md` · `reference/reference-data.md`
