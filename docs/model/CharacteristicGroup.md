---
part_of: MIS-QMS/docs/model
entity: CharacteristicGroup
order: 40
canon: true
rev: "1.01"
updated: 2026-09-06
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
- **The group exists only inside this database.** No such document is issued anywhere:
  it is our own construct for linking parts that share an assembly while numbering the
  same zone differently on their own drawings. Hence a group has **no revision of its
  own** — only a part's drawing revises (`Item.md`) (QMS-017).
- **Nominal and tolerance belong to the CG, not to the part.** Inside a group `g1` is
  one and the same physical dimension with one and the same tolerance for every part of
  the group — that is what the group is for. What stays local to a part is **only its
  local dimension number**. The values are filled in **once per group** and reused by all
  its parts (`decisions.md`, QMS-016).
- **The drawing itself belongs to the CG** (stored inside the database; PNG/JPEG,
  ≤5 MB) and is stored **as issued**: the engineering department releases it already
  ballooned — the callouts carry `G1…GN` instead of numbers. It is the drawing of the
  **assembly shared by the group's parts**, not the drawing of any one part; a part's own
  drawing, with its own revision, is not stored here. The application therefore
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
- **No versioning of a group** — not as a deferral but as a decision (QMS-017): a group
  is never re-valued in place; when its values move, a **clone** is made (see below).
  A second-level CG (linking constructively similar parts) is out of scope for now — it
  only imposes keeping the Item↔CG link many-to-many (`Item.md`).

### State and g-positions

- **State is not a separate axis** (see `Characteristic.md`): stages of one dimension
  are split into **separate g-positions** (invariant: a state change always changes
  both the local number and the value).
- There is no composite `(characteristic, state)` key; a mapping points to **one**
  g-position. Unmapped (non-CG) state dimensions stay two separate dimensions.

## Three kinds of event, and what each of them moves (QMS-017)

They are easy to confuse and they cost very differently.

| Event | Where it happens | What it moves |
|---|---|---|
| **The part's drawing is re-issued** (`A` → `B`) | the real world | a new revision of the part, cloned from the previous one (`Item.md`). Group links and mappings are re-stated **inside the new revision**; nothing already recorded changes |
| **The canon grows** — a position is added to a group | this database only | nothing in the real world; no part changes revision. The added position needs an answer from the group's **current** revisions (see below) |
| **The values move** — a tolerance or a nominal is re-issued for a family | the real world, via re-issued drawings | the group can no longer keep its promise for those parts → the group is **cloned** and the new revisions bind to the clone |

**Cloning a group.** The clone keeps the same `g1…gN` layout and takes the new values;
the mappings of the parts moving into their new revision are copied **by local number**,
so the common case — numbering intact, tolerance moved — costs one action for a whole
family instead of re-mapping a hundred parts by hand. Only a number that actually moved
is touched. Values are never edited in place: editing them would make old deviations read
against a tolerance that did not exist at their time.

**Adding a position rather than splitting the group.** When one part gains a dimension
the others do not have, the position is added **to the existing group** and the other
parts hold it under code 99. Splitting a group over a single extra dimension is the worse
trade: the whole value of grouping is that the more parts share a group, the more
precedents each of them gets.

- The new position needs an answer (a mapping, or code 99) **only from the revisions that
  are current**. Past revisions are left **unanswered** — that is the honest state, since
  the position was not in the canon when they were written, and stamping code 99 on them
  retroactively would assert a check nobody performed. Search is unaffected: a part with
  no answer and a part with code 99 are equally absent from a `(cg, g_index)` join.

**A group is never deactivated.** Parts of the previous issue keep arriving from the shop
for two to three months after a change, and past deviations stay searchable for good.
A group whose parts have all moved on is still a source — one the engineer raises by hand
when the automatic path finds nothing.

- **Marking, not deactivation:** a group is shown as a previous generation when **no part
  holds it in its current revision**. The state is **derived, not stored** — it needs no
  flag, no timer and no maintenance, and it cannot be forgotten in either direction.

## Mapping

- Links **(item revision, local#) → one canonical g-position** (single-field FK). The
  mapping carries no revision of its own: it hangs off the dimension and inherits the
  revision from it (`Characteristic.md`).
- Built **manually and incrementally**, assigned by a human. **Created early — before
  the deviation is registered** (buttons "Create mapping / link" sit in the deviation
  entry form, next to "Create Item"). See `_overview.md` §5–6.
- **Optional**: non-CG dimensions (the mass case) live without a canon.
- **One balloon = one local dimension = one link**, enforced both ways within one
  revision: a g-position takes a single dimension of a given part revision, and a
  dimension is linked to a single g-position. Re-linking a taken dimension is never
  silent — clear it first.
- Code **99** = "the part does not have this position" (a technical stub; a `g:99`
  pair explicitly records "the position was considered, it is absent"). Not a search
  key. **Physically it is the pair (item revision, g-position)** in its own table
  (`item_position_absent`), not a flag on the mapping row: the flag could not record
  *which* position was missing (`decisions.md`, S1 №6 revised — rev 0.2, QMS-013).
  Search by `(cg, g_index)` never returns such a part — there is nothing to join.
  **Code 99 is meaningful only where there is a group:** for a part revision with no CG
  link it has nothing to say and is not written.

> **Canon note (R2).** Retroactive mapping is treated as a data-loss risk and is
> **not** the default (this reverses session 06's "lazy resolve"; see
> `docs/decisions.md`, R2). The only exception is an **urgent WO**: the dimension may
> be registered unlinked and mapped later.

## Distinction from Zone

Zone and CG are distinct: **zone** is a soft search label (see `Finding.md`,
`reference/reference-data.md`); **CG** is the strict canon with geometry.

## Related

`Item.md` · `Characteristic.md` · `Finding.md` · `Search.md` · `reference/reference-data.md`
