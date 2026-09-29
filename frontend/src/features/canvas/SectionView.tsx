import { t } from "../../i18n/es-CL";
import type { IntentNode } from "./intentEditing";
import type { MemberGeometry, MemberSpec } from "./members";
import { normalizedSection } from "./Product3DScene";

/** §05-G technical output — a horizontal cut through a bay (the "detalle
 * de nodo" every fenestration drawing carries). The SAME normalized
 * member sections the 3D scene extrudes are drawn here in plan: exterior
 * at top, depth down the page. Members without a declared section draw
 * their approximate box as a dashed outline and say so — a convention,
 * never a declaration. */

const GLASS_DEFAULT_MM = 20;
const GASKET_MM = 3;
const PAD = 26;

type SectionSpec = {
  spec: MemberSpec;
  u0: number;
  v0: number;
  slotW: number;
  /** Plan depth the member occupies when no section polygon declares its
   * own — the fallback rectangle's height, separate from the v origin. */
  approxDepth: number;
};

function sectionPath(spec: SectionSpec): { d: string; approximate: boolean } {
  const section = normalizedSection(spec.spec);
  if (section === null) {
    return {
      d: `M ${spec.u0} ${spec.v0} h ${spec.slotW} v ${spec.approxDepth} h ${-spec.slotW} Z`,
      approximate: true,
    };
  }
  const uCenter = spec.u0 + spec.slotW / 2;
  const d = section.outline
    .map(
      ([u, v], index) =>
        `${index === 0 ? "M" : "L"} ${uCenter + u - section.width / 2} ${spec.v0 + v}`,
    )
    .join(" ");
  return { d: `${d} Z`, approximate: false };
}

export function SectionView({
  bay,
  members,
  widthMm,
}: {
  bay: IntentNode | null;
  members: MemberGeometry;
  widthMm: number;
}): JSX.Element {
  const depth = members.frame.section
    ? Number(members.frame.section.depth_mm) || members.rebateMm + members.sash.faceWidthMm
    : members.rebateMm + members.sash.faceWidthMm;
  const operable =
    bay !== null && bay.type === "BAY" && bay.opening_type != null && bay.opening_type !== "FIXED";
  const sashD = depth * 0.45;
  const glassT = Math.max(Number(bay?.glass_thickness_mm) || GLASS_DEFAULT_MM, 4);
  const glassZ = depth * 0.45;
  const bead = members.beadFor(bay?.glass_thickness_mm ?? null);
  // Approximate depth shares: the frame band sits above the sash band, so
  // an undeclared frame still draws its region — a convention, not a depth.
  const frameApprox = Math.max(depth - sashD, depth * 0.2);
  // A node detail only needs the two member joints — past a readable span
  // the drawing crops the glass mid-span with a conventional break mark,
  // so a 2 m bay doesn't flatten the section into a 20 px strip.
  const CROP_SPAN = 760;
  const cropped = widthMm > CROP_SPAN;
  const span = cropped ? CROP_SPAN : widthMm;
  const members_drawn: SectionSpec[] = [
    {
      spec: members.frame,
      u0: 0,
      v0: 0,
      slotW: members.frame.faceWidthMm,
      approxDepth: frameApprox,
    },
    {
      spec: members.frame,
      u0: span - members.frame.faceWidthMm,
      v0: 0,
      slotW: members.frame.faceWidthMm,
      approxDepth: frameApprox,
    },
  ];
  if (operable) {
    const sashW = Math.min(members.sash.faceWidthMm, widthMm / 3);
    members_drawn.push(
      {
        spec: members.sash,
        u0: members.rebateMm,
        v0: depth - sashD,
        slotW: sashW,
        approxDepth: sashD,
      },
      {
        spec: members.sash,
        u0: span - members.rebateMm - sashW,
        v0: depth - sashD,
        slotW: sashW,
        approxDepth: sashD,
      },
    );
  }
  const viewW = span + PAD * 2;
  const viewH = depth + PAD * 2 + 24;
  return (
    <svg
      className="section-view"
      viewBox={`${-PAD} ${-PAD - 18} ${viewW} ${viewH}`}
      role="img"
      aria-label={t("assembly.sectionView")}
    >
      <defs>
        <marker id="section-arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className="section-dim__arrow" />
        </marker>
      </defs>
      {/* exterior/interior labels */}
      <text x={-PAD + 2} y={-8} className="section-label">
        {t("assembly.sectionExterior")}
      </text>
      <text x={-PAD + 2} y={depth + 16} className="section-label">
        {t("assembly.sectionInterior")}
      </text>
      {/* member sections — declared polygons or dashed approximation */}
      {members_drawn.map((spec, index) => {
        const { d, approximate } = sectionPath(spec);
        return (
          <path
            key={`m-${index}`}
            d={d}
            className={`section-member section-member--${spec.spec.material.toLowerCase()}${approximate ? " section-member--approx" : ""}`}
          />
        );
      })}
      {/* glass line at its declared plane */}
      <rect
        x={members.frame.faceWidthMm + bead}
        y={glassZ}
        width={Math.max(span - 2 * (members.frame.faceWidthMm + bead), 2)}
        height={Math.min(glassT, 8)}
        className="section-glass"
      />
      {/* conventional break marks where a wide span is cropped */}
      {cropped &&
        [span * 0.42, span * 0.58].map((x, index) => (
          <path
            key={`break-${index}`}
            d={`M ${x - 6} ${glassZ + Math.min(glassT, 8) + 4} l 12 ${-(Math.min(glassT, 8) + 8)}`}
            className="section-break"
          />
        ))}
      {/* gasket dots at the glazing seat */}
      {[members.frame.faceWidthMm + bead - GASKET_MM, span - members.frame.faceWidthMm - bead].map(
        (x, index) => (
          <rect
            key={`g-${index}`}
            x={x}
            y={glassZ + Math.min(glassT, 8)}
            width={GASKET_MM}
            height={GASKET_MM}
            className="section-gasket"
          />
        ),
      )}
      {/* depth dimension */}
      <line
        x1={span + 10}
        y1={0}
        x2={span + 10}
        y2={depth}
        className="section-dim"
        markerStart="url(#section-arrow)"
        markerEnd="url(#section-arrow)"
      />
      <text
        x={span + 14}
        y={depth / 2}
        className="section-dim__text"
        transform={`rotate(90 ${span + 14} ${depth / 2})`}
      >
        {depth.toFixed(0)}
      </text>
      {/* legend note when any member is approximate */}
      {members_drawn.some((spec) => sectionPath(spec).approximate) && (
        <text x={-PAD + 2} y={depth + 30} className="section-approx">
          {t("assembly.sectionApproxNote")}
        </text>
      )}
    </svg>
  );
}
