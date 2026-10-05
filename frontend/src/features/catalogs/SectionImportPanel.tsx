/** §06-G — manufacturer section drawing import.
 *
 * Upload a DXF/SVG → the backend detects closed outlines → the reviewer
 * picks the right one and CONFIRMS the drawing→mm scale (guessed only from
 * declared units) → the polygon lands in the section editor as
 * DXF_REFERENCE with the stored document as its drawing_ref. Detection is
 * evidence for a human decision — nothing here writes authority by itself.
 */
import { useMemo, useRef, useState } from "react";

import type { SectionImportCandidate, SectionImportResponse } from "../../api/generated/models";
import { parseLocaleNumber } from "../../format";
import { t, type TranslationKey } from "../../i18n/es-CL";
import type { catalogApi } from "./catalogModel";

export interface SectionImportPick {
  vertices: { x_mm: string; y_mm: string }[];
  drawingRef: string;
}

// Coordinates and the user-confirmed scale are decimal strings — multiplying
// through binary floats rounds boundaries like 1.005 to the wrong hundredth.
// Keep the product exact in BigInt (section authority = mm decimals, never
// float) and round half away from zero to the contract's 2 decimals.
function parseDecimal(text: string): { num: bigint; den: bigint } | null {
  const match = /^(-?\d+)(?:\.(\d+))?$/.exec(text.trim());
  if (!match) return null;
  const frac = match[2] ?? "";
  return { num: BigInt(`${match[1]}${frac}`), den: 10n ** BigInt(frac.length) };
}

function scaleMmText(value: string, scaleText: string): string | null {
  const coord = parseDecimal(value);
  const scale = parseDecimal(scaleText);
  if (!coord || !scale) return null;
  const product = coord.num * scale.num * 100n;
  const divisor = coord.den * scale.den;
  const quotient = product / divisor;
  const remainder = product % divisor;
  const rounded =
    (remainder >= 0n ? remainder : -remainder) * 2n >= divisor
      ? quotient + (product >= 0n ? 1n : -1n)
      : quotient;
  const sign = rounded < 0n ? "-" : "";
  const absolute = rounded < 0n ? -rounded : rounded;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}

function bbox(points: [string, string][]): { minX: number; minY: number; w: number; h: number } {
  const xs = points.map(([x]) => Number(x));
  const ys = points.map(([, y]) => Number(y));
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return { minX, minY, w: Math.max(...xs) - minX, h: Math.max(...ys) - minY };
}

function CandidatePreview({
  points,
  className,
}: {
  points: [string, string][];
  className?: string;
}): JSX.Element {
  const box = bbox(points);
  const pad = Math.max(box.w, box.h) * 0.05 || 1;
  const path = points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x} ${y}`).join(" ");
  return (
    <svg
      className={className}
      viewBox={`${box.minX - pad} ${box.minY - pad} ${box.w + 2 * pad} ${box.h + 2 * pad}`}
      aria-hidden="true"
    >
      <path
        d={`${path} Z`}
        fill="none"
        stroke="currentColor"
        strokeWidth={Math.max(box.w, box.h) / 120}
      />
    </svg>
  );
}

export function SectionImportPanel({
  api,
  onApply,
  onClose,
}: {
  api: ReturnType<typeof catalogApi>;
  onApply: (pick: SectionImportPick) => void;
  onClose: () => void;
}): JSX.Element {
  const ct = (key: string) => t(`catalog.sectionImport.${key}` as TranslationKey);
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SectionImportResponse | null>(null);
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);
  const [scale, setScale] = useState("");

  const picked: SectionImportCandidate | null =
    result && pickedIndex !== null
      ? (result.candidates.find((candidate) => candidate.index === pickedIndex) ?? null)
      : null;

  const scaleText = useMemo(() => {
    const value = parseLocaleNumber(scale);
    return value !== null && value > 0 ? String(value) : null;
  }, [scale]);

  const scaledPoints = useMemo(() => {
    if (!picked || scaleText === null) return null;
    // Section contract: 0.01 mm precision, distinct vertices — rounding can
    // collapse adjacent sampled points, so dedupe consecutive equal pairs
    // and drop a closing repeat before the polygon ever reaches the API.
    const points: { x_mm: string; y_mm: string }[] = [];
    for (const [x, y] of picked.points) {
      if (x === undefined || y === undefined) return null;
      const x_mm = scaleMmText(x, scaleText);
      const y_mm = scaleMmText(y, scaleText);
      if (x_mm === null || y_mm === null) return null;
      const point = { x_mm, y_mm };
      const last = points[points.length - 1];
      if (last && last.x_mm === point.x_mm && last.y_mm === point.y_mm) continue;
      points.push(point);
    }
    const first = points[0];
    const last = points[points.length - 1];
    if (first && last && first.x_mm === last.x_mm && first.y_mm === last.y_mm) {
      points.pop();
    }
    return points.length >= 3 ? points : null;
  }, [picked, scaleText]);

  const scaledBox = useMemo(() => {
    if (!scaledPoints) return null;
    return bbox(scaledPoints.map((point) => [point.x_mm, point.y_mm]));
  }, [scaledPoints]);

  async function upload(file: File) {
    setBusy(true);
    setError("");
    setResult(null);
    setPickedIndex(null);
    setScale("");
    try {
      const data = await api.sectionImport(file);
      setResult(data);
      setScale(data.mm_per_unit ?? "");
      if (data.candidates.length === 1) setPickedIndex(data.candidates[0]!.index);
    } catch (cause) {
      const code = cause instanceof Error ? cause.message : "";
      setError(code.startsWith("section_") ? ct(`error.${code}`) : ct("error.failed"));
    } finally {
      setBusy(false);
    }
  }

  function confirm() {
    if (!result || !picked || !scaledPoints) return;
    onApply({ vertices: scaledPoints, drawingRef: result.document_path });
  }

  return (
    <section className="section-import" aria-label={ct("title")}>
      <header className="catalog-toolbar">
        <h4>{ct("title")}</h4>
        <button type="button" onClick={onClose}>
          {ct("close")}
        </button>
      </header>
      <p>{ct("help")}</p>

      <span className="file-field">
        <input
          ref={inputRef}
          type="file"
          accept=".dxf,.svg,image/svg+xml"
          className="file-input-hidden"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="ui-button ui-button--small"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {t("settings.fileChoose")}
        </button>
      </span>
      {busy && <p role="status">{ct("uploading")}</p>}
      {error && <p role="alert">{error}</p>}

      {result && (
        <>
          {result.warnings.length > 0 && (
            <ul className="section-import-warnings">
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          <p>{ct("pick")}</p>
          <ul className="section-import-candidates">
            {result.candidates.map((candidate) => (
              <li key={candidate.tag}>
                <button
                  type="button"
                  aria-pressed={pickedIndex === candidate.index}
                  className="section-import-candidate"
                  onClick={() => setPickedIndex(candidate.index)}
                >
                  <CandidatePreview points={candidate.points as [string, string][]} />
                  <span>{candidate.tag}</span>
                </button>
              </li>
            ))}
          </ul>

          {picked && (
            <div className="section-import-confirm">
              <label htmlFor="section-import-scale">
                <span>{ct("scale")}</span>
                <input
                  id="section-import-scale"
                  type="text"
                  required
                  inputMode="decimal"
                  data-pattern="[0-9]+([.,][0-9]+)?"
                  value={scale}
                  onChange={(event) => setScale(event.target.value)}
                />
              </label>
              <small>{ct("scaleHelp")}</small>
              {scaledPoints && scaledBox && (
                <div className="section-import-preview">
                  <CandidatePreview
                    points={scaledPoints.map((point) => [point.x_mm, point.y_mm])}
                    className="section-import-preview-figure"
                  />
                  <p>
                    {ct("preview")}: {scaledBox.w.toFixed(1)} × {scaledBox.h.toFixed(1)} mm
                  </p>
                </div>
              )}
              <button type="button" className="primary" disabled={!scaledPoints} onClick={confirm}>
                {ct("apply")}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
