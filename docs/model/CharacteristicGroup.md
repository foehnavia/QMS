---
part_of: MIS-QMS/docs/model
entity: CharacteristicGroup
order: 40
canon: true
rev: "1.00"
updated: 2026-09-02
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
- **Nominal and tolerance belong to the CG, not to the part.** Inside a group `g1` is
  one and the same physical dimension with one and the same tolerance for every part of
  the group — that is what the group is for. What stays local to a part is **only its
  local dimension number**. The values are filled in **once per group** and reused by all
  its parts (`decisions.md`, QMS-016).
- **The drawing itself belongs to the CG** (stored inside the database; PNG/JPEG,
  ≤5 MB) and is stored **as issued**: the engineering department releases it already
  ballooned — the callouts carry `G1…GN` instead of numbers. The application therefore
  **does not place balloons of its own**: it shows the drawing as a visual reference and
  keeps the positions in a **table** (index · nominal · tolerance `+` · tolerance `−`).
  Having the operator re-place balloons over the picture was both duplicated work and the
  main source of a wrong binding — the picture does not reliably say which dimension was
  meant, and the whole cross-part search rests on that binding (`decisions.md`, QMS-016).
  The coordinate columns `g_position.x`/`y` survive in the schema **unfilled**; dropping
  them is not worth a migration. Size threshold for drawings: `architecture.md` §4–§5.
- **The number of positions is stated when the group is created** — the table is laid out
  at once for `g1…gN` after the drawing. A g-position is **internal machinery of the
  cross-part search** and is never shown to the end user, so it carries no human-readable
  label: its meaning is read off the drawing.
- **Form and position tolerances** (e.g. concentricity to datum A) are entered as ordinary
  positions. Neither the kind of tolerance nor the datum is stored — they are on the
  drawing, and all the system needs from a position is to relate one part's dimension to
  another's. GD&T is not modelled in stage 1 (`decisions.md`, QMS-016).
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
  to anything can be deleted at all (`decisions.md`, QMS-016). With the table laid out by the number
  of positions on the drawing, the issued indices coincide with the drawing's labels on
  their own — there is nothing left to decide at entry.
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
