---
part_of: MIS-QMS/docs/specs
spec: cg-editor-and-mapping
status: as-built
task: QMS-013
amended_by: QMS-016
rewritten: 2026-09-03
updated: 2026-09-03
---

# CG editor & mapping dialog — as-built spec (S3 / QMS-013, rewritten after QMS-016)

> As-built. Sprint S3 delivered the first version (worklog `0003-cg-mapping.md`, accepted
> 2026-08-11); the run QMS-016 rebuilt the format — balloons removed, binding made part of
> creating a part. This text describes **what is in the build now**, not what S3 delivered. Model canon: `../model/CharacteristicGroup.md`. Schema:
> `../architecture.md` §5 (rev 0.2). Behavioural source: `../model/_history/Session-03.md` §4.

## 1. Where it lives

| Entry point | Opens | Note |
|---|---|---|
| Section **"Characteristic groups"** | CG list → editor / mapping | admin path; works without any Item |
| Item screen → **"Mapping…"** | mapping dialog for the selected part | part's own CG if it has exactly one, otherwise a picker |
| **"Create item"** with a group chosen | mapping dialog, at once | binding is part of creating the part — see §4a |
| Deviation entry form | mapping dialog via `MappingDialog.run(...)` | the "early buttons" of R2 — canon binding *before* registration |
| Deviation card | same dialog | from a finding whose dimension is not bound |

`MappingDialog.run(engine, item_id, cg_id, parent) -> bool` is the public call point.

## 2. The drawing is a reference, not a canvas (QMS-016, worklog `0014`)

**Balloons are gone.** The drawing is issued by the design office **already marked**: the
callouts carry `G1…GN`. The application no longer places balloons over the image and stores no
coordinates. Re-marking by hand was double work and the main source of binding error — and the
whole cross-part search rests on that binding.

- the drawing is loaded as is, shown full width, with zoom and panning; it is the surface the
  operator reads the position from;
- positions are kept in a **table**: index · nominal · upper deviation · lower deviation;
- the number of positions is set when the group is created; the table unfolds to `g1…gN`, and
  the indexes then match the drawing by construction;
- a g-position carries **no label**: the position is internal machinery of the cross-search and
  is never shown as a name.

**Nominal and deviations belong to the group, not to the part.** Inside a CG, `g1` is one
physical dimension with one tolerance for every part; the part keeps only its local number.
(Moving them onto the part was proposed by the session and **rejected** by the user.)

**Limit deviations follow ISO 286** (worklog `0015`): each carries **its own sign** — an
interference fit has both in plus. The invariant is **upper ≥ lower**; there is no sign check.
Labels: `Upper deviation` · `Lower deviation`, composite cell `Limit deviations`. A zero
deviation is written **without a sign**.

## 3. CG editor

- Edits a group: name, positions (index, nominal, limit deviations), drawing load/drop.
- Changes accumulate in the form and commit as **one transaction on "Save"**. The exception is
  deleting a position: occupancy is checked on click, so the operator is told immediately.
- **The form does not lose what was typed** (worklog `0016`): adding or deleting a position and
  swapping the drawing keep the entered values. The rule "edits accumulate until Save" is about
  the **database**, and does not license the form to drop input between two clicks inside itself.
- **A position in use cannot be removed** — counted over both mappings and "absent" marks.
- **The index of an existing position is read-only** (identity, see canon).
- Form tolerances (coaxiality) are entered as ordinary positions; the tolerance kind and datum
  are not stored — they live on the drawing, and the system needs only to relate one part's
  dimension to another's.
- The window opens maximisable: the drawing is a work surface, not an illustration.

## 4. Mapping dialog

- Layout: the **drawing on top**, the table below — `Position · State · Local number ·
  Canon geometry`. Geometry is shown because binding is the moment the operator decides, and
  sending them to another dialog for a number is worse than showing it here.
- Three states per position: **linked** (local number), **absent (99)**, **undecided**.
- The local number is typed **straight into the row**; the characteristic is created if it does
  not exist yet (same domain function as the non-CG auto-create). An emptied cell does **not**
  clear a binding — clearing has its own button.
- **Writes happen per action**, not on the button — hence the labels **"Done" / "Close"**.
- **"Done" is always enabled and checks** (QMS-016, worklog `0020`): pressing it closes the open
  cell editor first, so the last typed number counts, then asks the domain for completeness and
  names the positions still undecided. This supersedes the S3 wording "enabled by completeness":
  the meaning stands, the mechanism changed — completeness is asked of the **state**, not encoded
  in a button.
- The window opens maximisable, like the editor.

## 4a. Binding is part of creating a part (QMS-016, worklog `0018`)

> **A part with a group assigned does not exist in the database with an incomplete mapping.**

- "Create item" with a group chosen opens the mapping dialog **at once**; the part-creation form
  no longer asks for local numbers at all (it had no drawing to read them from);
- every position must get a state — a local number or code 99;
- **refusing the mapping cancels the creation**: the part and everything written during the
  session are removed, after a confirmation. A part that already carries deviations or findings
  is never discarded — that guard also keeps the road open for Q-15.

Why: at deviation entry only the local number is known. With an incomplete mapping the dimension
is silently created as non-CG, the deviation lands outside the canon, and this surfaces later —
when L1b fails to find what it should.

Existing parts get a **warning without a ban** on closing with undecided positions: their
records are already written and there is nothing to roll back. The proper mechanism — a snapshot
before re-mapping, a warning about references, a conflict registry — is **Q-15**.

## 5. Invariants enforced in the domain (not the form)

- one position = one dimension = one link, both directions;
- re-linking a taken dimension is refused with a named message ("clear it first");
- binding clears a prior "absent" mark and vice versa;
- drawing must be PNG/JPEG **by file signature**, ≤5 MB;
- a group must have at least one position.

## 6. Related

`../model/CharacteristicGroup.md` · `../model/Item.md` · `../architecture.md` §4–§5 ·
`../decisions.md` · `../worklog/0003-cg-mapping.md` · `0014` · `0015` · `0016` · `0018` · `0020`
