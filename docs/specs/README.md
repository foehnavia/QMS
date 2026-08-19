# specs/ — UI & interaction specifications

> **Stub.** This directory holds UI / interaction specs, to be filled during the
> design/build stage (not part of the model concept). Q-06 decision: forms & UI live
> here, **not inline** in the model files (`docs/decisions.md`).

Planned specs (from `50_MIS-QMS/PROPOSAL_MIS-QMS_structure` §4.1 and the concept):

- **Add Item** form — create a part; seed CG dimensions; create a missing CG on the
  fly (`../model/Item.md`, `../model/CharacteristicGroup.md`).
- **Deviation entry** form — header, findings `1..N`, early canon binding (R2), decision as a
  separate action, inspection on a finding →
  **`deviation-entry.md` (as-built, S4 / QMS-014)**.
- **Visual CG editor & mapping dialog** — balloons `g1…gN` over the CG drawing →
  **`cg-editor-and-mapping.md` (as-built, S3 / QMS-013)**.
- **Deviation card** — automatic prior-deviation overview, exact (L1) and descriptive (L2)
  precedent search, decision taken from the card →
  **`deviation-card.md` (as-built, S5 / QMS-015)**.
- **Deep search** — query constructor, read-only, stage 1.5 (`../model/Search.md`,
  `../staging.md`).
- **Document generation** — `אישור חריגה` export (later stage;
  `../model/reference/output-document.md`).

Specs are written **as-built**: the sprint's naryad designs the UI, the accepted result is
recorded here. Model canon stays in `../model/` — specs never restate it, they link.
