import { useId } from "react";

import type { ColorOptionChoice } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";

/** D05: real finish picker — the declared catalog drives the swatches, the
 * face availability drives which chips can be picked per face, and the
 * engine's combination rules are previewed client-side so an impossible
 * pair is named before the request leaves. The API remains the authority;
 * nothing here fabricates an option or a reason. */

/** The engine's whole-bar kinds — an anodized bar takes its finish through
 * the whole section, so it can never carry a different second face. */
const WHOLE_BAR_KINDS = new Set(["ANODIZED"]);

export function optionFaces(option: ColorOptionChoice): { interior: boolean; exterior: boolean } {
  return {
    interior: option.faces !== "EXTERIOR_ONLY",
    exterior: option.faces !== "INTERIOR_ONLY",
  };
}

/** Mirrors `resolve_color_selection`: the client-side pre-flight so the
 * disabled Guardar names the real blocker before the round trip. */
export function combinationIssue(
  options: readonly ColorOptionChoice[],
  bicolorAllowed: boolean,
  interiorCode: string,
  exteriorCodeRaw: string,
): string | null {
  if (!options.length || !interiorCode) return null;
  const exteriorCode = exteriorCodeRaw || interiorCode;
  const interior = options.find((option) => option.code === interiorCode);
  const exterior = options.find((option) => option.code === exteriorCode);
  // A code the catalog doesn't declare is handled by the undeclared-finish
  // guard, not by combination rules.
  if (!interior || !exterior) return null;
  if (!optionFaces(interior).interior) {
    return t("projects.colorFaceForbidden")
      .replace("{name}", interior.name)
      .replace("{face}", t("projects.colorFaceInterior"));
  }
  if (!optionFaces(exterior).exterior) {
    return t("projects.colorFaceForbidden")
      .replace("{name}", exterior.name)
      .replace("{face}", t("projects.colorFaceExterior"));
  }
  if (interior.code === exterior.code) return null;
  if (!bicolorAllowed) {
    return t("projects.colorBicolorForbidden")
      .replace("{exterior}", exterior.name)
      .replace("{interior}", interior.name);
  }
  for (const option of [interior, exterior]) {
    if (WHOLE_BAR_KINDS.has(option.kind)) {
      return t("projects.colorWholeBar").replace("{name}", option.name);
    }
  }
  if (interior.kind === "MASS" && exterior.kind === "MASS") {
    return t("projects.colorTwoMass")
      .replace("{exterior}", exterior.name)
      .replace("{interior}", interior.name);
  }
  for (const [option, other] of [
    [interior, exterior],
    [exterior, interior],
  ] as const) {
    if (option.pair_code && other.code !== option.pair_code) {
      return t("projects.colorPairRequires")
        .replace("{name}", option.name)
        .replace("{pair}", option.pair_code);
    }
  }
  return null;
}

/** Surcharge hint under the swatch — the catalog's own label when declared,
 * else nothing (never a fabricated amount). */
function surchargeHint(option: ColorOptionChoice | null): string | null {
  return option?.surcharge_label || null;
}

function SwatchChip({
  option,
  selected,
  face,
  disabled,
  onPick,
}: {
  option: ColorOptionChoice;
  selected: boolean;
  face: "interior" | "exterior";
  disabled: boolean;
  onPick(code: string): void;
}): JSX.Element {
  const allowed = optionFaces(option)[face];
  const forbidden = !allowed;
  // A chip forbidden in this row is only made on the OPPOSITE face — the
  // tooltip must name the face where the finish exists, not this row's.
  const title = forbidden
    ? t(face === "interior" ? "projects.colorExteriorOnly" : "projects.colorInteriorOnly")
    : option.manufacturer_code || undefined;
  const sheenId = useId();
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      className={`color-chip${selected ? " is-selected" : ""}${forbidden ? " is-forbidden" : ""}`}
      disabled={disabled || forbidden}
      title={title}
      data-code={option.code}
      data-face={face}
      onClick={() => onPick(option.code)}
    >
      <span
        className="color-chip__swatch"
        style={option.render_color ? { background: option.render_color } : undefined}
        aria-hidden="true"
      >
        {/* Declared texture motif — §10 forbids CSS gradient literals, so the
         * catalog texture renders as inline SVG geometry. */}
        {option.render_texture === "WOOD_GRAIN" && (
          <svg viewBox="0 0 24 24" preserveAspectRatio="none" aria-hidden>
            <path
              d="M4 -1c3 7 -2 13 1 26M10 -1c-2 9 3 15 -1 26M17 -1c3 8 -2 16 2 26M22 -1c-2 8 3 14 -1 26"
              stroke="rgba(0,0,0,0.22)"
              strokeWidth="1.2"
              fill="none"
            />
          </svg>
        )}
        {option.render_texture === "ANODIZED" && (
          <svg viewBox="0 0 24 24" preserveAspectRatio="none" aria-hidden>
            <linearGradient id={sheenId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="rgba(255,255,255,0.55)" />
              <stop offset="0.5" stopColor="rgba(255,255,255,0)" />
              <stop offset="1" stopColor="rgba(0,0,0,0.3)" />
            </linearGradient>
            <rect width="24" height="24" fill={`url(#${sheenId})`} />
          </svg>
        )}
      </span>
      <span className="color-chip__name">{option.name}</span>
    </button>
  );
}

export function ColorSelector({
  options,
  bicolorAllowed,
  colorInterior,
  colorExterior,
  disabled,
  onChange,
}: {
  options: readonly ColorOptionChoice[];
  bicolorAllowed: boolean;
  colorInterior: string;
  /** "" means same-as-interior (monocolor). */
  colorExterior: string;
  disabled: boolean;
  onChange(color: string, colorExterior: string): void;
}): JSX.Element {
  const sameFaces = !colorExterior || colorExterior === colorInterior;
  const exteriorCode = sameFaces ? colorInterior : colorExterior;
  const issue = combinationIssue(
    options,
    bicolorAllowed,
    colorInterior,
    sameFaces ? "" : colorExterior,
  );
  // A stored code the catalog doesn't declare still displays — once — so
  // the field is honest; it stays unsaveable via the editor's guard.
  const orphanCodes = (code: string): readonly string[] =>
    code && !options.some((option) => option.code === code) ? [code] : [];
  const interiorName =
    options.find((option) => option.code === colorInterior)?.name ?? colorInterior;
  const exteriorName = options.find((option) => option.code === exteriorCode)?.name ?? exteriorCode;
  const interiorHint =
    surchargeHint(options.find((option) => option.code === colorInterior) ?? null) ?? null;
  const exteriorHint = sameFaces
    ? null
    : (surchargeHint(options.find((option) => option.code === exteriorCode) ?? null) ?? null);

  const pick = (face: "interior" | "exterior", code: string): void => {
    if (face === "interior") {
      onChange(code, sameFaces ? "" : colorExterior);
    } else {
      onChange(colorInterior, code === colorInterior ? "" : code);
    }
  };

  const faceRow = (face: "interior" | "exterior", value: string): JSX.Element => (
    <div
      className="color-selector__face"
      role="radiogroup"
      aria-label={t(face === "interior" ? "projects.colorInterior" : "projects.colorExterior")}
    >
      <span className="color-selector__face-label">
        {t(face === "interior" ? "projects.colorInterior" : "projects.colorExterior")}
      </span>
      <div className="color-selector__chips">
        {options.map((option) => (
          <SwatchChip
            key={`${face}-${option.code}`}
            option={option}
            selected={option.code === value}
            face={face}
            disabled={disabled}
            onPick={(code) => pick(face, code)}
          />
        ))}
        {orphanCodes(value).map((code) => (
          <button
            key={`${face}-orphan-${code}`}
            type="button"
            role="radio"
            aria-checked="true"
            className="color-chip is-selected is-undeclared"
            disabled
            title={t("projects.colorNotDeclared")}
            data-code={code}
          >
            <span
              className="color-chip__swatch color-chip__swatch--undeclared"
              aria-hidden="true"
            />
            <span className="color-chip__name">{code}</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="color-selector" data-testid="color-selector">
      {faceRow("interior", colorInterior)}
      {bicolorAllowed && (
        <label className="color-selector__same">
          <input
            type="checkbox"
            checked={sameFaces}
            disabled={disabled}
            onChange={(event) => {
              if (event.target.checked) {
                onChange(colorInterior, "");
                return;
              }
              // Splitting the faces needs an exterior value that differs
              // from the interior — sameFaces derives from equality, so
              // echoing the interior code would re-check the box and the
              // bicolor row could never appear.
              const alt = options.find(
                (option) => option.code !== colorInterior && optionFaces(option).exterior,
              );
              onChange(colorInterior, alt?.code ?? "");
            }}
          />
          <span>{t("projects.colorSameFaces")}</span>
        </label>
      )}
      {bicolorAllowed && !sameFaces && faceRow("exterior", exteriorCode)}
      <p className="color-selector__summary">
        {sameFaces
          ? interiorName
          : t("projects.colorSummary")
              .replace("{exterior}", exteriorName)
              .replace("{interior}", interiorName)}
        {interiorHint && <span className="color-selector__hint"> · {interiorHint}</span>}
        {exteriorHint && <span className="color-selector__hint"> · {exteriorHint}</span>}
      </p>
      {issue && (
        <p className="color-selector__issue" role="alert">
          {issue}
        </p>
      )}
    </div>
  );
}
