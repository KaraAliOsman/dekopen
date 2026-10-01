import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import { t } from "../../i18n/es-CL";

export type SignaturePadHandle = {
  dataURL: () => string | null;
  renderTyped: (name: string) => void;
  clear: () => void;
};

const WIDTH = 480;
const HEIGHT = 160;

/** A drawn-signature capture: pointer strokes on a canvas, exported as PNG. */
const SignaturePad = forwardRef<SignaturePadHandle, { onDraw?: (hasDrawing: boolean) => void }>(
  function SignaturePad({ onDraw }, ref) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const drawing = useRef(false);
    const strokes = useRef(0);
    const [empty, setEmpty] = useState(true);

    useImperativeHandle(ref, () => ({
      dataURL: () =>
        strokes.current > 0 && canvasRef.current ? canvasRef.current.toDataURL("image/png") : null,
      renderTyped: (name: string) => {
        // Typed-name signature — the same PNG artifact a drawn signature
        // produces, so the sealed POD is identical in kind. Keyboard-only
        // receivers sign with their name; the canvas stays draw-capable.
        const canvas = canvasRef.current;
        const ctx = canvas?.getContext("2d");
        if (!canvas || !ctx) return;
        ctx.clearRect(0, 0, WIDTH, HEIGHT);
        ctx.strokeStyle = getComputedStyle(canvas).color;
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = "italic 500 34px Georgia, 'Times New Roman', serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(name, WIDTH / 2, HEIGHT / 2 - 6, WIDTH - 40);
        ctx.font = "11px sans-serif";
        ctx.globalAlpha = 0.55;
        ctx.fillText(t("production.signatureTypedMark"), WIDTH / 2, HEIGHT - 18);
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.moveTo(60, HEIGHT - 34);
        ctx.lineTo(WIDTH - 60, HEIGHT - 34);
        ctx.stroke();
        strokes.current = 1;
        setEmpty(false);
        onDraw?.(true);
      },
      clear: () => {
        const ctx = canvasRef.current?.getContext("2d");
        ctx?.clearRect(0, 0, WIDTH, HEIGHT);
        strokes.current = 0;
        setEmpty(true);
        onDraw?.(false);
      },
    }));

    useEffect(() => {
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (!canvas || !ctx) return;
      ctx.strokeStyle = getComputedStyle(canvas).color;
      ctx.lineWidth = 2;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      const point = (event: PointerEvent) => {
        const rect = canvas.getBoundingClientRect();
        return {
          x: ((event.clientX - rect.left) / rect.width) * WIDTH,
          y: ((event.clientY - rect.top) / rect.height) * HEIGHT,
        };
      };
      let drew = false;
      const down = (event: PointerEvent) => {
        event.preventDefault();
        canvas.setPointerCapture(event.pointerId);
        drawing.current = true;
        drew = false;
        const { x, y } = point(event);
        ctx.beginPath();
        ctx.moveTo(x, y);
      };
      const move = (event: PointerEvent) => {
        if (!drawing.current) return;
        const { x, y } = point(event);
        ctx.lineTo(x, y);
        ctx.stroke();
        drew = true;
      };
      const up = (event: PointerEvent) => {
        if (!drawing.current) return;
        drawing.current = false;
        if (canvas.hasPointerCapture(event.pointerId)) {
          canvas.releasePointerCapture(event.pointerId);
        }
        // A tap without movement seals no signature — only inked strokes count.
        if (!drew) return;
        strokes.current += 1;
        if (strokes.current === 1) {
          setEmpty(false);
          onDraw?.(true);
        }
      };
      const cancel = (event: PointerEvent) => {
        drawing.current = false;
        drew = false;
        if (canvas.hasPointerCapture(event.pointerId)) {
          canvas.releasePointerCapture(event.pointerId);
        }
      };
      canvas.addEventListener("pointerdown", down);
      canvas.addEventListener("pointermove", move);
      canvas.addEventListener("pointerup", up);
      canvas.addEventListener("pointercancel", cancel);
      return () => {
        canvas.removeEventListener("pointerdown", down);
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerup", up);
        canvas.removeEventListener("pointercancel", cancel);
      };
    }, [onDraw]);

    return (
      <div className="signature-pad">
        <canvas
          ref={canvasRef}
          width={WIDTH}
          height={HEIGHT}
          className="signature-pad-canvas"
          role="img"
          aria-label={t("production.deliverySignatureLabel")}
        />
        {empty ? (
          <span className="signature-pad-hint">{t("production.deliverySignatureHint")}</span>
        ) : null}
      </div>
    );
  },
);

export default SignaturePad;
