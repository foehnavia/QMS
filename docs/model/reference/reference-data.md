---
part_of: MIS-QMS/docs/model
entity: reference-data
order: 110
canon: true
rev: "1.00"
updated: 2026-08-10
---

# Reference data — prepared in advance vs. created on the fly

> Reference tables the model attaches to. Entry point: `_overview.md`.

Part of the reference data is maintained by an administrator so the system has
something to attach to. But an important caveat: **most data is entered during
deviation processing, not beforehand.** While the database is being populated, the
most common scenario is: you start processing a deviation, discover that the dimension
or the whole part is not yet in the system, enter what is needed, and continue. This
is the normal working path, not an exception.

## Tables

- **Item type, connection type, size** — basic part classifiers (`Item.md`).
  Connection type (`C1`, `V3`, `IntHex`, `LYNX`, `General` = default) and size (`NP`,
  `SP`, `WP`, `General` = default) each have a `General` default so a part can be
  created even when the specifics are not yet relevant.
- **CharacteristicGroups (CG) and their g-positions** — a small stable reference
  (~20–30 groups system-wide). Each group defines reference positions `g1…gN` with
  nominal and tolerance taken from the drawing. Normally maintained by the
  administrator, but a missing group **may also be created on the fly**, at the moment
  a part is created (`CharacteristicGroup.md`; `docs/decisions.md`, R3).
- **Zone** — unique zones defined for part types or families that share common
  construction and purpose; within one zone, dimensional characteristics of different
  parts may have different values and different numbering. A **soft search label**
  placed on findings (`Finding.md`, `Search.md`).
- **Deviation type** — a descriptive characteristic of the deviation itself, to find
  similar cases more precisely when exact matches are absent (e.g. thread burr, thread
  length, inner diameter, cutting-edge width, angle, …). Together with zone, this is
  the **second search level** (`Search.md`). Both zone and deviation-type are populated
  by the operator at entry and cleaned by the administrator.
- **Inspection (research) types** — the list of research kinds (initially, e.g.
  `Solidworks assembly` and `Implantation torque test`; extended as needed;
  `Inspection.md`).

## Related

`Item.md` · `CharacteristicGroup.md` · `Finding.md` · `Inspection.md` · `Search.md`
