# DEKOPEN Orb — design spec

Companion mock: `dekopen-orb.html` (standalone, renders all states × sizes × themes).

## 1. Concept

A refined **anthracite sphere** with **twin casement-slot eyes** — two rounded
vertical slots echo a paired casement window, which makes the face
fenestration-native and DEKOPEN's own rather than a generic dot-eyed blob.

Two orthogonal channels:

- **Eyes = life.** Pose, blink, and gaze direction communicate *what the orb is
  doing* (resting, scanning, raised-attention, joy, worry, dimmed).
- **Ring = semantics.** A thin arc outside the sphere carries status color only
  when the state needs it — the same hues and positions as `.aiws-state` pills
  (`accent` working, `warning` waiting, `success`, `danger`). Hidden otherwise.
  Status lives on the ring, never on the face.

Token contract honored: no glow filters, no glassmorphism, no decorative
gradients on UI surfaces. The sphere's micro-shading is *material*, not
decoration — it reuses the member-anthracite palette (`#3f454b` family), so the
orb reads as DEKOPEN's own charcoal-antracite hardware.

## 2. SVG structure

`viewBox="0 0 48 48"`; outer ring at `r=21.5`, body `r=17` → ~15% breathing
room so the arc never clips at any size.

```html
<svg class="orb is-{state}" viewBox="0 0 48 48" width="{size}" height="{size}" aria-hidden="true">
  <defs>
    <radialGradient id="{uid}-body" cx="38%" cy="28%" r="80%">
      <stop offset="0"   stop-color="var(--orb-hi)"/>   <!-- .s0 -->
      <stop offset="55%" stop-color="var(--orb-mid)"/>  <!-- .s1 -->
      <stop offset="100%" stop-color="var(--orb-lo)"/>  <!-- .s2 -->
    </radialGradient>
  </defs>

  <!-- semantics channel: hidden unless the state shows it -->
  <circle class="orb__ring" cx="24" cy="24" r="21.5"/>

  <!-- life channel: everything that tilts/breathes lives in this group -->
  <g class="orb__tilt">
    <circle class="orb__body" cx="24" cy="24" r="17" fill="url(#{uid}-body)"/>
    <ellipse class="orb__bounce" cx="29" cy="33" rx="6" ry="2.6"
             transform="rotate(-18 29 33)"/>                    <!-- teal floor bounce, 10% -->
    <ellipse class="orb__spec" cx="18" cy="15.5" rx="5.4" ry="3"
             transform="rotate(-26 18 15.5)"/>                  <!-- crisp specular -->

    <g class="orb__eyes orb__eyes--open">                        <!-- default face -->
      <rect class="orb__eye" x="15.6" y="20" width="6" height="9.4" rx="3"/>
      <rect class="orb__eye" x="26.4" y="20" width="6" height="9.4" rx="3"/>
      <circle class="orb__glint" cx="17.8" cy="22.4" r="1"/>
      <circle class="orb__glint" cx="28.6" cy="22.4" r="1"/>
    </g>
    <g class="orb__eyes orb__eyes--joy">                         <!-- success: ∩ ∩ -->
      <path d="M15.8 26.6 Q18.6 22.2 21.4 26.6"/>
      <path d="M26.6 26.6 Q29.4 22.2 32.2 26.6"/>
    </g>
    <g class="orb__eyes orb__eyes--worry">                       <!-- error: inner-up slits -->
      <rect x="15.8" y="23.4" width="5.8" height="3.4" rx="1.7" transform="rotate(-14 18.7 25.1)"/>
      <rect x="26.4" y="23.4" width="5.8" height="3.4" rx="1.7" transform="rotate(14 29.3 25.1)"/>
    </g>
    <g class="orb__eyes orb__eyes--flat">                        <!-- canceled: neutral slits -->
      <rect x="15.8" y="23.9" width="5.8" height="3" rx="1.5"/>
      <rect x="26.4" y="23.9" width="5.8" height="3" rx="1.5"/>
    </g>
  </g>
</svg>
```

Element inventory:

| element        | role                                                        |
|----------------|-------------------------------------------------------------|
| `orb__ring`    | status arc; `opacity:0` by default                          |
| `orb__tilt`    | scale/rotate/translate rig for breathe, lift, settle, shake |
| `orb__body`    | sphere; radial gradient + 1px edge stroke                   |
| `orb__bounce`  | faint teal floor reflection — brand echo, not glow          |
| `orb__spec`    | crisp white specular ellipse, upper-left                    |
| `orb__eyes--*` | exactly one set visible per state                           |
| `orb__glint`   | micro eye highlights; dropped under 28px (`orb--s`)         |

## 3. Animation approach

**CSS keyframes only.** No SMIL (dead-end API, no theme cascade), no JS
(no timers, survives SSR, pauses in background tabs for free, honors
`prefers-reduced-motion` in one media query). State = one class on `<svg>`;
React re-render swaps the class, transitions are declarative.

Shared rigs (on `.orb__tilt` / `.orb__eyes` / `.orb__ring`, all with
`transform-box:fill-box; transform-origin:center`):

| keyframe            | used by        | effect                                        |
|---------------------|----------------|-----------------------------------------------|
| `orb-breathe`       | idle/queued*/thinking/working/success(tail) | scale 1↔1.028, period varies by state (2.6s working … 6.4s queued) |
| `orb-blink`         | idle, working  | scaleY dip 0.1 at ~94% of 5–6s loop            |
| `orb-blink-lidded`  | queued         | baseline scaleY .6, dip .12 at 88% of 7s       |
| `orb-scan`          | thinking       | eyes translateX ±2.4px, scaleX .86, 1.7s      |
| `orb-waitlook`      | waiting        | eyes raised −2.4px + double-blink at 76–88%    |
| `orb-orbit`         | working        | ring rotate 360° / 1.35s linear                |
| `orb-ringpulse`     | waiting        | ring opacity .55↔1, 1.7s                       |
| `orb-settle`        | success        | one-shot scale .92→1.06→1, .55s, then breathe resumes at 1s |
| `orb-shake`         | error          | one-shot translateX −1.6/+1.3px, .38s          |

Ring geometry: circumference ≈ 135. `working` = `dasharray 34 101` orbiting.
`waiting`/`success`/`error` = `dasharray 30 105`, `dashoffset 15`, group
rotated −90° → a short arc centered at top (a "headline" mark).

Static pose differences (no keyframes needed): waiting tilts the whole rig
`translateY(-1px) rotate(-2.5deg)`; canceled is `opacity:.5`.

Reduced motion: `@media (prefers-reduced-motion: reduce)` kills every
animation; states degrade to their static pose (waiting keeps raised eyes,
working keeps the arc mid-orbit position — still legible).

## 4. Color / highlight values

All through CSS vars — add to `tokens.css` next to the theme blocks:

| var             | light        | dark                 | source                                  |
|-----------------|--------------|----------------------|-----------------------------------------|
| `--orb-hi`      | `#4e5960`    | `#5a666e`            | member-anthracite-highlight family      |
| `--orb-mid`     | `#262e34`    | `#272f35`            | member-anthracite fill/edge blend       |
| `--orb-lo`      | `#12171b`    | `#10151a`            | signature-ink, deepened                 |
| `--orb-edge`    | `rgba(18,24,28,.55)` | `rgba(233,242,241,.16)` | silhouette separation           |
| `--orb-spec-op` | `.5`         | `.32`                | specular strength                       |
| `--orb-eye`     | `#eaf3f1`    | `#eaf3f1`            | frosted-lite white (same both themes)   |
| ring colors     | `--theme-accent` / `--theme-warning` / `--theme-success` / `--theme-danger` | same vars (dark variants resolve automatically) | existing tokens — zero new status hues |

The sphere is *intentionally identical* in both themes (identity = the black
orb); only the edge stroke and specular opacity adapt, which is what separates
it from `#14181a` dark canvas. The teal bounce uses `var(--theme-accent)` at
10% so it shifts with the theme automatically.

## 5. State machine — job.state → orb state

Server states from `AiJobDetail.state` (`AgentBody.tsx`, `AssistantWorkspacePage.tsx`):

| job state                       | orb        | eyes                         | ring                    | motion                          |
|---------------------------------|------------|------------------------------|-------------------------|----------------------------------|
| `QUEUED`                        | `queued`   | half-lidded                  | —                       | 6.4s shallow breath              |
| `PLANNING`                      | `thinking` | open, scanning               | —                       | gaze pendulum 1.7s               |
| `RUNNING`                       | `working`  | open, steady                 | accent arc orbiting     | breath 2.6s                      |
| `WAITING_FOR_USER`, `WAITING_FOR_APPROVAL` | `waiting` | open, raised      | warning arc, pulsing    | tilt toward viewer + double-blink |
| `SUCCEEDED`                     | `success`  | joy ∩                        | success arc (static)    | one-shot settle pop              |
| `FAILED`, `FAILED_RETRYABLE`    | `error`    | worried slits                | danger arc (static)     | one-shot shake                   |
| `CANCELED`                      | `canceled` | neutral slits                | —                       | none; opacity .5                 |
| no job / dock closed            | `idle`     | open                         | —                       | breath 4.6s + occasional blink   |

One mapping helper:

```ts
export function orbStateFor(jobState?: string): OrbState {
  switch (jobState) {
    case "QUEUED": return "queued";
    case "PLANNING": return "thinking";
    case "RUNNING": return "working";
    case "WAITING_FOR_USER":
    case "WAITING_FOR_APPROVAL": return "waiting";
    case "SUCCEEDED": return "success";
    case "FAILED":
    case "FAILED_RETRYABLE": return "error";
    case "CANCELED": return "canceled";
    default: return "idle";
  }
}
```

## 6. Placement

| surface                              | size | state source                                   |
|--------------------------------------|------|------------------------------------------------|
| launcher button (replaces `◈` in `ask-dock__trigger`) | 20 | `idle`; `working` while a job is live on this surface |
| dock header (`ask-dock__header`)     | 28 | live `jobState` from `AgentBody`               |
| message/turn avatar (agent turns in `.ask-dock__thread`, `.aiws-turn--agent`) | 28 | `success` on settled turn; `waiting` while questions pending |
| workspace empty state (`.aiws` main) | 64 | `waiting` — inviting the first goal            |
| artifact cards (`.aiws-artifact`)    | 16–20 corner mark | `success` static                |
| approval prompts / ops steps (`.ask-dock__ops`, `.aiws-questions`) | 28 | `waiting`                             |
| job rail rows (`.aiws-job`)          | 20 | mapped from `job.state`                        |

Sizing rule: `size < 28` adds `orb--s` → hides `orb__glint` + `orb__bounce`
(silhouette + eyes stay clean at favicon scale). Sizes are free — `20, 28, 64`
are the placements, not a restriction.

## 7. React component

```tsx
export type OrbState =
  | "idle" | "queued" | "thinking" | "working"
  | "waiting" | "success" | "error" | "canceled";

export function Orb({
  state = "idle",
  size = 28,
  title,                       // optional a11y label; omit when decorative
}: {
  state?: OrbState;
  size?: number;
  title?: string;
}): JSX.Element {
  const uid = useId();         // gradient ids must be unique per instance
  return (
    <svg
      className={`orb is-${state}${size < 28 ? " orb--s" : ""}`}
      viewBox="0 0 48 48" width={size} height={size}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {/* markup from §2 with url(#${uid}-body) */}
    </svg>
  );
}
```

Implementation notes:

- **CSS lives in `assistant.css`** (or a new `orb.css` imported once); state
  classes `.is-*` on the `<svg>` element drive everything — the component
  holds zero animation logic.
- **`useId()` for the gradient** — duplicate `id="orbBody"` across mounted
  orbs would all resolve to the first instance (works visually since defs are
  identical, but correct ids avoid edge cases with dedup/hydration).
- All animatable groups need `transform-box: fill-box; transform-origin:
  center` — SVG transforms default to the viewport origin otherwise.
- `prefers-reduced-motion` is handled in CSS only; no prop needed.
- Do not pass `state` raw from the API — always through `orbStateFor()` so
  unknown future states degrade to `idle`.
- Decorative use: `aria-hidden` (default). Status-bearing use (job rail):
  pass `title={stateLabel(job.state)}` so screen readers get text, not a
  mystery icon — matches the existing `.aiws-state` pill pattern.

## 8. What the design deliberately avoids

- No single-eye, blob, or sparkle motifs (other vendors' marks).
- No glow/bloom filters — the tokens forbid them and the specular ellipse +
  edge stroke carry the "premium" read instead.
- No gradients on *UI surfaces* — the sphere's shading is confined to the
  orb's own artwork and reuses the anthracite material values.
- No mouth. Mouths are where mascot identities go childish; the eyes + ring
  carry the whole range this product needs.
