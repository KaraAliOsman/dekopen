import { type PointerEvent, useMemo, useState } from "react";

import type { EngineCalculateResponse } from "../../api/generated/models";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { type CanvasDesignInputs, type DimensionAxis, useCanvasStore } from "./canvasStore";
import { EditableDimension } from "./EditableDimension";
import { fixedPresentationGeometry, toSvgNumber } from "./presentationGeometry";
import { presentationNumberToDecimal, snapOuterDimension, type SnapResult } from "./snapping";

type CADViewportSvgProps = {
  inputs: CanvasDesignInputs;
  response: EngineCalculateResponse;
  disabled: boolean;
  onCommit(axis: DimensionAxis, candidate: string): Promise<boolean>;
  onEditStart(): void;
};

type DragState = {
  axis: DimensionAxis;
  pointerId: number;
};

type SnapGuide = SnapResult & {
  axis: DimensionAxis;
};

function pointerCandidate(
  event: PointerEvent<SVGCircleElement>,
  axis: DimensionAxis,
  snapEnabled: boolean,
  setViewport: ReturnType<typeof useCanvasStore.getState>["setViewport"],
): SnapResult {
  const svg = event.currentTarget.ownerSVGElement;
  const matrix = svg?.getScreenCTM();
  if (svg === null || svg === undefined || matrix === null || matrix === undefined) {
    throw new Error("SVG viewport transformation is unavailable");
  }
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
  const pixelsPerMm = Math.hypot(matrix.a, matrix.b);
  setViewport({ scale: pixelsPerMm, offsetX: matrix.e, offsetY: matrix.f });
  return snapOuterDimension(
    presentationNumberToDecimal(axis === "width" ? point.x : point.y),
    presentationNumberToDecimal(pixelsPerMm),
    snapEnabled,
  );
}

export function CADViewportSvg({
  inputs,
  response,
  disabled,
  onCommit,
  onEditStart,
}: CADViewportSvgProps): JSX.Element {
  // Stable across draft-dimension keystrokes and pointer drags.
  const geometry = useMemo(() => fixedPresentationGeometry(inputs, response), [inputs, response]);
  const draftDimension = useCanvasStore((state) => state.draftDimension);
  const setDraftDimension = useCanvasStore((state) => state.setDraftDimension);
  const snapEnabled = useCanvasStore((state) => state.snapEnabled);
  const setViewport = useCanvasStore((state) => state.setViewport);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [guide, setGuide] = useState<SnapGuide | null>(null);

  const draftNumber =
    drag !== null && draftDimension?.axis === drag.axis ? toSvgNumber(draftDimension.value) : null;
  const previewWidth = drag?.axis === "width" && draftNumber !== null ? draftNumber : null;
  const previewHeight = drag?.axis === "height" && draftNumber !== null ? draftNumber : null;

  function updateDrag(event: PointerEvent<SVGCircleElement>, axis: DimensionAxis): SnapResult {
    const snapped = pointerCandidate(event, axis, snapEnabled, setViewport);
    setDraftDimension({ axis, value: snapped.valueMm });
    setGuide({ ...snapped, axis });
    return snapped;
  }

  function beginDrag(axis: DimensionAxis, event: PointerEvent<SVGCircleElement>): void {
    if (disabled) return;
    event.preventDefault();
    onEditStart();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ axis, pointerId: event.pointerId });
    updateDrag(event, axis);
  }

  function moveDrag(event: PointerEvent<SVGCircleElement>): void {
    if (drag === null || drag.pointerId !== event.pointerId) return;
    updateDrag(event, drag.axis);
  }

  function finishDrag(event: PointerEvent<SVGCircleElement>): void {
    if (drag === null || drag.pointerId !== event.pointerId) return;
    const axis = drag.axis;
    const snapped = updateDrag(event, axis);
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDrag(null);
    void onCommit(axis, snapped.valueMm).finally(() => setGuide(null));
  }

  function cancelDrag(event: PointerEvent<SVGCircleElement>): void {
    if (drag === null || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
    setGuide(null);
    setDraftDimension(null);
  }

  return (
    <section className="cad-viewport" aria-labelledby="canvas-title">
      <div className="cad-viewport__heading">
        <div>
          <p className="eyebrow">Vano demo · G1</p>
          <h1 id="canvas-title">Editor paramétrico 2D</h1>
        </div>
        <span className="canvas-system">{t("catalog.demo")}</span>
      </div>
      <svg
        className="cad-svg"
        data-testid="canvas-svg"
        viewBox={geometry.viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="group"
        aria-label={t("canvas.paneEditableDims")}
      >
        <title>{t("canvas.paneComputed")}</title>
        <line className="dimension-line" x1="0" y1="-46" x2={geometry.nominalWidth} y2="-46" />
        <line className="dimension-tick" x1="0" y1="-62" x2="0" y2="-30" />
        <line
          className="dimension-tick"
          x1={geometry.nominalWidth}
          y1="-62"
          x2={geometry.nominalWidth}
          y2="-30"
        />
        <line className="dimension-line" x1="-66" y1="0" x2="-66" y2={geometry.nominalHeight} />
        <line className="dimension-tick" x1="-82" y1="0" x2="-50" y2="0" />
        <line
          className="dimension-tick"
          x1="-82"
          y1={geometry.nominalHeight}
          x2="-50"
          y2={geometry.nominalHeight}
        />

        <rect
          className="frame-outline"
          data-testid="fixed-frame"
          x="0"
          y="0"
          width={geometry.nominalWidth}
          height={geometry.nominalHeight}
        />
        <rect
          className="glass-pane"
          data-testid="fixed-glass"
          data-width-mm={response.glasses[0]?.width_mm}
          data-height-mm={response.glasses[0]?.height_mm}
          x={geometry.glassX}
          y={geometry.glassY}
          width={geometry.glassWidth}
          height={geometry.glassHeight}
        />
        <text
          className="opening-label"
          x={geometry.nominalWidth / 2}
          y={geometry.nominalHeight / 2 - 14}
          textAnchor="middle"
        >
          FIXED
        </text>
        <text
          className="glass-dimension"
          data-testid="canvas-glass-dimension"
          x={geometry.nominalWidth / 2}
          y={geometry.nominalHeight / 2 + 26}
          textAnchor="middle"
        >
          {fmtMm(response.glasses[0]?.width_mm)} × {fmtMm(response.glasses[0]?.height_mm)} mm
        </text>

        {previewWidth !== null ? (
          <rect
            className="resize-preview"
            x="0"
            y="0"
            width={previewWidth}
            height={geometry.nominalHeight}
          />
        ) : null}
        {previewHeight !== null ? (
          <rect
            className="resize-preview"
            x="0"
            y="0"
            width={geometry.nominalWidth}
            height={previewHeight}
          />
        ) : null}
        {guide?.showGuide === true ? (
          guide.axis === "width" ? (
            <rect
              className="snap-guide"
              data-testid="snap-guide"
              x={toSvgNumber(guide.valueMm) - 2}
              y="0"
              width="4"
              height={geometry.nominalHeight}
            />
          ) : (
            <rect
              className="snap-guide"
              data-testid="snap-guide"
              x="0"
              y={toSvgNumber(guide.valueMm) - 2}
              width={geometry.nominalWidth}
              height="4"
            />
          )
        ) : null}

        <EditableDimension
          axis="width"
          acceptedValue={inputs.nominalWidthMm}
          label={t("canvas.nominalWidthMm")}
          x={geometry.nominalWidth / 2 - 95}
          y={-100}
          disabled={disabled}
          onCommit={onCommit}
          onEditStart={onEditStart}
        />
        <EditableDimension
          axis="height"
          acceptedValue={inputs.nominalHeightMm}
          label={t("canvas.nominalHeightMm")}
          x={-226}
          y={geometry.nominalHeight / 2 - 21}
          disabled={disabled}
          onCommit={onCommit}
          onEditStart={onEditStart}
        />

        <circle
          className="resize-handle"
          data-testid="resize-width"
          aria-label={t("canvas.resizeWidth")}
          cx={geometry.nominalWidth}
          cy={geometry.nominalHeight / 2}
          r="18"
          tabIndex={0}
          onPointerCancel={cancelDrag}
          onPointerDown={(event) => beginDrag("width", event)}
          onPointerMove={moveDrag}
          onPointerUp={finishDrag}
        />
        <circle
          className="resize-handle"
          data-testid="resize-height"
          aria-label={t("canvas.resizeHeight")}
          cx={geometry.nominalWidth / 2}
          cy={geometry.nominalHeight}
          r="18"
          tabIndex={0}
          onPointerCancel={cancelDrag}
          onPointerDown={(event) => beginDrag("height", event)}
          onPointerMove={moveDrag}
          onPointerUp={finishDrag}
        />
      </svg>
    </section>
  );
}
