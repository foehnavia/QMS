---
part_of: MIS-QMS/docs/specs
spec: cg-editor-and-mapping
status: as-built
task: QMS-013
updated: 2026-08-11
---

# Visual CG editor & mapping dialog — as-built spec (S3 / QMS-013)

> As-built: describes what sprint S3 delivered (worklog `0003-cg-mapping.md`), reviewed
> and accepted 2026-08-11. Model canon: `../model/CharacteristicGroup.md`. Schema:
> `../architecture.md` §5 (rev 0.2). Behavioural source: `../model/_history/Session-03.md` §4.

## 1. Where it lives

| Entry point | Opens | Note |
|---|---|---|
| Section **"Группы характеристик"** (main window) | CG list → editor / mapping | admin path; works without any Item |
| Item screen → **"Привязка к канону…"** | mapping dialog for the selected part | part's own CG if it has exactly one, otherwise a picker |
| Deviation entry form (**S4**) | mapping dialog via `MappingDialog.run(...)` | the "early buttons" of R2 — canon binding *before* registration |

`MappingDialog.run(engine, item_id, cg_id, parent) -> bool` is the public call point.
S4 hangs its buttons on it; nothing else is re-implemented.

## 2. Balloon canvas (shared)

- Background: the CG drawing, scaled to fit, aspect preserved. **No drawing → balloons
  fall back to a grid** and everything else behaves identically.
- Balloons `g1…gN`: circles, label isolated (`U+2068…U+2069`) so LTR labels keep their
  order inside the RTL window.
- Coordinates are **normalised 0..1** of the image, never pixels: window resizing and a
  re-scanned drawing of another resolution leave balloons on the same spot.
- Two modes: **edit** (drag to place) and **select** (click to act).

## 3. CG editor

- Edits a group: name, positions (`g_index`, nominal, tolerance ±), balloon placement,
  drawing load/drop.
- Changes accumulate in the form and commit as **one transaction on "Сохранить"**. The
  exception is deleting a position: occupancy is checked on click, so the operator is
  told immediately rather than at save time.
- **A position in use cannot be removed** — counted over both mappings and "absent"
  marks; the message states how many references hold it.
- **`g_index` of an existing position is read-only** (identity, see canon). New rows are
  editable until saved.
- Dropping or replacing the drawing **keeps** the coordinates; re-cropped scans are
  re-placed by hand (known behaviour, `decisions.md`).

## 4. Mapping dialog

- Per balloon, three states: **linked** (bright green, shows the local number),
  **absent** — code 99 (grey), **undecided** (neutral).
- Click a balloon → enter the part's local dimension number → linked. The characteristic
  is created if it does not exist yet (same domain function as the non-CG auto-create).
- "Нет у детали (99)" records the pair (item, g-position); "Очистить" returns the pair to
  undecided **without deleting the dimension** — a dimension exists independently of the
  canon.
- **Completion gate:** the confirm button is enabled only when every balloon has a state
  (Session-03 §4). Undecided positions are listed in the status line.
- **Writes happen per action**, not on the button; the button confirms completeness and
  closes — hence the labels **"Готово" / "Закрыть"**, not Save/Cancel (`decisions.md`).

## 5. Invariants enforced in the domain (not the form)

- one balloon = one dimension = one link, both directions;
- re-linking a taken dimension is refused with a named message ("clear it first");
- binding clears a prior "absent" mark and vice versa;
- coordinates must be within 0..1;
- drawing must be PNG/JPEG **by file signature**, ≤5 MB.

## 6. Related

`../model/CharacteristicGroup.md` · `../model/Item.md` · `../architecture.md` §4–§5 ·
`../decisions.md` · `../worklog/0003-cg-mapping.md`
