---
part_of: MIS-QMS/docs/model
entity: Item
order: 20
canon: true
rev: "1.01"
updated: 2026-09-06
---

# Item

> The manufactured part (`item_number`). **Center of the model** — almost every
> grouping, sorting and query runs "from the part". Entry point: `_overview.md`.

## Definition

A manufactured product with its own catalog number (item number). Around it live its
**revisions** (see below) and, under each revision, its **dimensions**
(`Characteristic.md`), the **deviations** recorded against those dimensions
(`Deviation.md`), and the **canonical layer** (`CharacteristicGroup.md`) that lets the
same physical feature be compared across different parts.

## Attributes

- `item_number` — catalog / item number (key).
- Reference classifiers: `item_type`, `connection_type`, `size` — see
  `reference/reference-data.md`. Each of `connection_type` and `size` has a
  `General` default, so a part can be created even when the specifics are not yet
  relevant.
- **Revisions** `1..N` — see below. Note that the dimensions, the CG links and the
  code-99 rows do **not** hang off the Item itself: they belong to one of its
  revisions.

## Revision (QMS-017)

A revision is a property of **the part's drawing**, not of our data. Engineering
re-issues the drawing on any change — a design change, a dimension added for a zone
that was not checked before, a tolerance or a nominal moved — and the new issue carries
the next designation (`A` → `B`). A characteristic group has **no revision of its own**:
the group is our construct and does not exist outside this database
(`CharacteristicGroup.md`).

- **The item number stays one record.** A revision is a child record of the Item, so a
  re-issued drawing never creates a twin part.
- A revision is a **designation, not a number** — entered as issued. Their order is
  stored explicitly, because the system must be able to name "the previous one", and
  exactly one revision of a part is the **current** one.
- **What belongs to a revision and not to the part:**
  - its dimensions (`Characteristic.md`) — key `(item, revision, local#)`;
  - its links to characteristic groups;
  - its code-99 rows (`CharacteristicGroup.md`).

  **Mapping and findings need no revision of their own:** both hang off a dimension and
  inherit the revision from it. The revision therefore enters the schema at exactly one
  point — the owner of the dimension — and everything downstream follows.
- **Entered by hand when the part is created** (a rare, deliberate act; a silent default
  would be wrong here). **Auto-filled with the current revision when a deviation is
  registered**, with a separate manual action to move it to a previous one: parts of the
  previous issue keep arriving from the shop for two to three months after a change.
- **A new revision is created by cloning the previous one.** The form opens already
  filled with the previous revision's local numbers, group links and code-99 rows; the
  operator edits only what actually changed. This is what keeps the rare "all numbers
  moved" case from costing more than the common "one tolerance moved" case — the action
  is the same either way.
- **Re-linking a renumbered dimension to its counterpart in the previous revision is not
  built in stage 1.** Statistically ~95 % of re-issues move no local number at all, or
  move one or two; the rest is tolerances and nominal values, with the numbering intact.
  When it is needed, the planned shape is **lazy**: bind this revision's dimension to the
  previous revision's dimension **at the moment a deviation appears** on that part, so a
  family of a hundred parts is never re-mapped in one go. Consequence accepted for now: a
  precedent whose local number moved between revisions is not found automatically — it is
  raised by hand, from the previous revision's records.

## Invariants

- An Item revision with **0 CG links is the mass case**.
- An Item never has **0 characteristics** once it exists: a part enters the base at
  its first deviation, and a deviation is always tied to dimensions.
- On revision creation only the **CG dimensions** are seeded (into that revision); other
  dimensions are created automatically on the first deviation that references them (no
  form) — see `Characteristic.md`, `_overview.md` §6.
- **A deviation and all its findings live in one revision:** every finding points at a
  dimension of the revision recorded on the deviation (`Deviation.md`).

## CG link

- The link is **many-to-many** ("for growth"; the interface currently assigns 0..1). It
  is held by the **revision**, not by the Item: a part may leave a group at `B` while its
  `A` keeps it. Several groups on one part is the intended direction (a part carries
  several distinct assemblies) but stays **out of stage 1** — see `CharacteristicGroup.md`
  and `decisions.md`.

## Not carried over

- The two hidden Airtable rollup fields used for reports are **not** carried into this
  model.

## Related

`Characteristic.md` · `CharacteristicGroup.md` · `Deviation.md` · `reference/reference-data.md`
