import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { CanvasViewport } from "./CanvasViewport";
import {
  clampViewToBox,
  FIT_PADDING,
  fitTransform,
  PAN_MARGIN,
  panBy,
  shouldRefitView,
  unionBox,
  zoomAt,
} from "./viewport";

const BOX = { x: -170, y: -150, w: 2100, h: 1670 };

it("fit centers the content box with padding", () => {
  const view = fitTransform(BOX, 1000, 700);
  // Centered: screen center = container center.
  expect(view.tx + (BOX.x + BOX.w / 2) * view.scale).toBeCloseTo(500, 1);
  expect(view.ty + (BOX.y + BOX.h / 2) * view.scale).toBeCloseTo(350, 1);
  expect(view.scale).toBeCloseTo(
    Math.min((1000 - FIT_PADDING * 2) / 2100, (700 - FIT_PADDING * 2) / 1670),
    4,
  );
});

it("zoomAt keeps the anchor point fixed on screen", () => {
  const view = { scale: 0.4, tx: 100, ty: 50 };
  const zoomed = zoomAt(view, 300, 200, 1.5);
  // mm point under (300,200) before = same after.
  const mmX = (300 - view.tx) / view.scale;
  const mmY = (200 - view.ty) / view.scale;
  expect(zoomed.tx + mmX * zoomed.scale).toBeCloseTo(300, 4);
  expect(zoomed.ty + mmY * zoomed.scale).toBeCloseTo(200, 4);
});

it("zoom clamps at the bounds and pan translates", () => {
  const view = { scale: 0.4, tx: 0, ty: 0 };
  expect(zoomAt(view, 0, 0, 1e6).scale).toBeLessThanOrEqual(6);
  expect(zoomAt(view, 0, 0, 1e-6).scale).toBeGreaterThanOrEqual(0.03);
  const moved = panBy(view, 10, -20);
  expect(moved).toMatchObject({ tx: 10, ty: -20 });
});

it("clampViewToBox keeps a margin of content on-screen", () => {
  // Content stranding: a huge pan that would put the whole box off-canvas
  // gets pulled back so PAN_MARGIN px stay visible.
  const fitted = fitTransform(BOX, 1000, 700);
  const stranded = panBy(fitted, -5000, 0);
  const clamped = clampViewToBox(stranded, BOX, 1000, 700);
  const right = (BOX.x + BOX.w) * clamped.scale + clamped.tx;
  expect(right).toBeCloseTo(PAN_MARGIN, 1);
  // A normal pan inside bounds is untouched.
  const small = panBy(fitted, -30, -15);
  expect(clampViewToBox(small, BOX, 1000, 700)).toBe(small);
  // Both directions stranded at once.
  const corner = clampViewToBox(panBy(fitted, 5000, 5000), BOX, 1000, 700);
  const left = BOX.x * corner.scale + corner.tx;
  const top = BOX.y * corner.scale + corner.ty;
  expect(left).toBeCloseTo(1000 - PAN_MARGIN, 1);
  expect(top).toBeCloseTo(700 - PAN_MARGIN, 1);
});

it("a content epoch bump refits even after manual pan/zoom", () => {
  expect(
    shouldRefitView({
      contentEpochChanged: true,
      boxChanged: true,
      containerResized: false,
      userInteracted: true,
    }),
  ).toBe(true);
});

it("auto-fit follows box/container changes only while the view is automatic", () => {
  // Once the user pans or zooms, a contentBox change must NOT jump the view
  // back — the async plan arriving later must not steal the camera.
  expect(
    shouldRefitView({
      contentEpochChanged: false,
      boxChanged: true,
      containerResized: false,
      userInteracted: true,
    }),
  ).toBe(false);
  expect(
    shouldRefitView({
      contentEpochChanged: false,
      boxChanged: true,
      containerResized: true,
      userInteracted: false,
    }),
  ).toBe(true);
});

it("unionBox wraps both boxes", () => {
  const union = unionBox({ x: -10, y: -20, w: 100, h: 50 }, { x: 50, y: 10, w: 80, h: 120 });
  expect(union).toMatchObject({ x: -10, y: -20, w: 140, h: 150 });
});

it("renders the island controls and opens the zoom menu", () => {
  render(
    <CanvasViewport contentBox={BOX} selectionBox={null} status="2.100 × 1.400 mm">
      <rect data-testid="content" width={10} height={10} />
    </CanvasViewport>,
  );
  expect(screen.getByTestId("assembly-sheet")).toBeTruthy();
  expect(screen.getByTestId("content")).toBeTruthy();
  expect(screen.getByLabelText("Alejar")).toBeTruthy();
  expect(screen.getByLabelText("Acercar")).toBeTruthy();
  expect(screen.getByText("2.100 × 1.400 mm")).toBeTruthy();
  // Pre-fit state renders at 100%.
  expect(screen.getByLabelText("Opciones de zoom").textContent).toBe(`${Math.round(100)}%`);
  fireEvent.click(screen.getByLabelText("Opciones de zoom"));
  // The island fit button plus the menu's item both carry this name.
  expect(screen.getAllByRole("button", { name: /Ajustar a la vista/ }).length).toBe(2);
  const selection = screen.getByRole("button", { name: /Ajustar a la selección/ });
  expect((selection as HTMLButtonElement).disabled).toBe(true);
});
