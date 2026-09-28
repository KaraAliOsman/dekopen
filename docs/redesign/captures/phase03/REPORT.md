# Phase-03 fenestration render evidence — @1079dc2 (superset of b8bc600)

Captured on the live wt-commercial stack (Vite :5173, CDP-attached Chrome, real
orbit/pose interactions). Benchmark matrix is the public route — no auth.
Diagnostic evidence captured in Studio logged in as demo-estimator.

## A. Benchmark matrix (public route)
- `benchmark-page-{pvc,pvcfoil,alu}.png` — full page per finish chip (1440-wide)
- `benchmark-<fixture>-{pvc,pvcfoil,alu}-3d.png` — 3D card activated ("Orbitar"),
  exterior-ish live view. 11 fixtures × 3 finishes = 33 files.

## B. Hardware close-ups (viewport crops, not page thumbnails)
- `hw-lever-tiltturn.png` — casement lever: rose plate + collar + tapered arm
- `hw-hinge-tiltturn.png` — rebate-edge hinge (dark box/knuckle at the rebate)
- `hw-escutcheon-door-interior.png` — door escutcheon + thumb-turn (interior)
- `hw-escutcheon-door-exterior.png` — door escutcheon + cylinder (exterior)
- `hw-pull-sliding-cup.png` — sliding flush cup (uñero) on meeting stile
- `hw-centrelever-awning.png` — awning bottom-rail centre lever
- `hw-tophinge-awning.png` — awning top hinge barrel

## C. Motion states — recorded video
- screencast `rec-37b9cdc4-…` (clean): tilt-turn Cerrar→Abrir (side-pivot swing)
  →Abatir (bottom-pivot tilt)→Cerrar; leaf+glass+hardware move together; caption
  "Posición ilustrativa" appears while posed, clears on close; repeated toggles
  show no transform accumulation; sliding leaf travels its rail only.

## D. Theme invariance
- `theme-{light,dark}-{pvc,alu}.png`, `theme-invariance-{pvc,alu}.png` —
  frame pixel RGB is byte-identical across themes; only the stage/ground flip.

## E. Diagnostics honesty
- `diag-chips-3d.png`, `studio-handle-outofrange.png`,
  `diag-handle-outofrange-2d.png`, `diag-handle-ring-zoom.png` — handle height
  2500mm on a 1400mm leaf → 3D chips "Herraje esquemático" + "Altura de manilla
  fuera de rango"; 2D alzado shows the red dashed danger ring (handle-datum-flag)
  + SVG title "Altura declarada 2500 mm cae fuera de la hoja". NOT silently clamped.

## F. 2D handedness
- `2d-alzado-tiltturn.png` — TILT_TURN_LEFT: handle marker on right stile,
  opposite the left hinges (correct).
- `2d-alzado-door.png` — DOOR_ENTRY leaf: hinge ticks on the left (outer) stile,
  handle on the right (meeting) stile (correct opposite-hinge convention).

## Physical defects observed
- **Steel/handle materials render near-black** — lever, escutcheon, hinges read as
  flat dark silhouettes rather than metallic steel. Cause: `--model3d-handle`
  (#4a5055) / `--model3d-steel` (#a9b2b8) surfaces carry `metalness` up to 0.9,
  but the scene has NO environment map (ambient + 2 directional lights only).
  High-metalness PBR with nothing to reflect → collapses to black. Geometry is
  correct (rose/collar/taper, escutcheon plate, hinge barrel) but the material
  flattens it. Fix direction: lower metalness or add a subtle env/stage HDRI.
- **Sliding tirador (surface bar) not reachable on the benchmark** — every sliding
  fixture binds `KIT-SLIDING` ("uñero embutido") → only the flush cup renders; the
  `surface_pull`/`lift_slide` bar needs a "tirador/asa/elevable" kit (not seeded
  into any fixture). Flush cup verified; tirador path unexercised.
- **Hinge detail is subtle** — reads as a dark box/step at the rebate; the knuckle
  barrel + flag silhouette is present but low-contrast at typical zoom.
- No interpenetrations, no wrong-face hardware, glass reads translucent (not
  opaque), arcs render smooth (not faceted), no silent clamps.

## Diagnostic paths
- `handle_out_of_range` → "Altura de manilla fuera de rango" chip + 2D red dashed
  ring + SVG title. WORKS.
- `hardware_convention` → "Herraje esquemático" chip (DEMO kit is approximate).
  WORKS.
- `kit_unknown` → "Kit no resuelto" — not exercised (all bound kits resolve);
  chip mechanism proven by the other two.
