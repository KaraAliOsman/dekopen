import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";

export type GlassPiece = {
  bay_id: string;
  leaf_id?: string | null;
  width_mm: string;
  height_mm: string;
  area_m2?: string;
  weight_kg?: string | null;
  thickness_net_mm?: string | null;
  glass_spec?: string | null;
  article_sku?: string | null;
};
export type PolishingEntry = {
  bay_id: string;
  leaf_id?: string | null;
  edges?: { top?: boolean; right?: boolean; bottom?: boolean; left?: boolean };
};

// Engine decimals stay exact: values are scaled to 1e-6 integer mantissas
// (BigInt) — never routed through binary floats.
const SCALE = 1_000_000n;
function scaled(value: string | number | undefined): bigint {
  const text = String(value ?? "0").trim() || "0";
  const negative = text.startsWith("-");
  const body = negative ? text.slice(1) : text;
  const [intPart = "0", fracPart = ""] = body.split(".");
  if (!/^\d+$/.test(intPart) || !/^\d*$/.test(fracPart)) return 0n;
  const mantissa = BigInt(intPart) * SCALE + BigInt((fracPart + "000000").slice(0, 6));
  return negative ? -mantissa : mantissa;
}
function fmtScaled(value: bigint, dp: number): string {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(7, "0");
  const intPart = digits.slice(0, -6) || "0";
  const fracPart = digits.slice(-6).slice(0, dp);
  return `${negative ? "-" : ""}${intPart}.${fracPart}`;
}

type Group = {
  spec: string;
  sku: string;
  thickness: string;
  pieces: { piece: GlassPiece; edges: string }[];
  qty: number;
  areaScaled: bigint;
  weightScaled: bigint;
  weightUnknown: boolean;
};

function polishKey(bay: string, leaf: string | null | undefined): string {
  return `${bay}|${leaf ?? "-"}`;
}

function edgeLabel(edges: PolishingEntry["edges"] | undefined): string {
  if (!edges) return "—";
  const parts: string[] = [];
  if (edges.top) parts.push(t("production.glassEdgeTop"));
  if (edges.right) parts.push(t("production.glassEdgeRight"));
  if (edges.bottom) parts.push(t("production.glassEdgeBottom"));
  if (edges.left) parts.push(t("production.glassEdgeLeft"));
  return parts.length ? parts.join("·") : "—";
}

type SizeRow = {
  dims: string;
  edges: string;
  count: number;
  areaScaled: bigint;
  weightScaled: bigint;
  weightUnknown: boolean;
};

function sizeRows(group: Group): SizeRow[] {
  const perSize = new Map<string, SizeRow>();
  for (const item of group.pieces) {
    const dims = `${fmtMm(item.piece.width_mm)}×${fmtMm(item.piece.height_mm)}`;
    const key = `${dims}|${item.edges}`;
    const entry = perSize.get(key) ?? {
      dims,
      edges: item.edges,
      count: 0,
      areaScaled: 0n,
      weightScaled: 0n,
      weightUnknown: false,
    };
    entry.count += 1;
    entry.areaScaled += scaled(item.piece.area_m2);
    if (item.piece.weight_kg == null) {
      entry.weightUnknown = true;
    } else {
      entry.weightScaled += scaled(item.piece.weight_kg);
    }
    perSize.set(key, entry);
  }
  return [...perSize.values()];
}

function weightText(scaledWeight: bigint, quantity: number, unknown: boolean): string {
  return unknown
    ? t("production.glassWeightUnknown")
    : fmtScaled(scaledWeight * BigInt(quantity), 2);
}

export function glassSummaryCsv(groups: Group[], quantity: number): string {
  const rows: string[][] = [
    [
      t("production.glassColSpec"),
      t("production.glassColSku"),
      t("production.glassColThickness"),
      t("production.glassColDims"),
      t("production.glassColQty"),
      t("production.glassColArea"),
      t("production.glassColWeight"),
      t("production.glassColPolish"),
    ],
  ];
  let totalQty = 0;
  let totalArea = 0n;
  let totalWeight = 0n;
  let totalUnknown = false;
  for (const group of groups) {
    for (const row of sizeRows(group)) {
      rows.push([
        group.spec,
        group.sku,
        group.thickness,
        row.dims,
        String(row.count * quantity),
        fmtScaled(row.areaScaled * BigInt(quantity), 4),
        weightText(row.weightScaled, quantity, row.weightUnknown),
        row.edges,
      ]);
    }
    totalQty += group.qty;
    totalArea += group.areaScaled;
    totalWeight += group.weightScaled;
    totalUnknown ||= group.weightUnknown;
  }
  rows.push([
    t("production.glassTotals"),
    "",
    "",
    "",
    String(totalQty * quantity),
    fmtScaled(totalArea * BigInt(quantity), 4),
    weightText(totalWeight, quantity, totalUnknown),
    "",
  ]);
  // `;` separator + BOM so the sheet opens correctly in Excel on es-CL locales
  // (`,` parses columns wrong and UTF-8 accents garble without the BOM).
  return (
    "\uFEFF" +
    rows
      .map((row) =>
        row.map((cell) => (/[";\n]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell)).join(";"),
      )
      .join("\n")
  );
}

export function GlassSummary({
  glasses,
  polishing,
  quantity = 1,
  onExport,
}: {
  glasses: GlassPiece[];
  polishing: PolishingEntry[];
  quantity?: number;
  onExport: (groups: Group[]) => void;
}) {
  const polishByKey = new Map(
    polishing.map((entry) => [polishKey(entry.bay_id, entry.leaf_id), entry]),
  );
  const groups = new Map<string, Group>();
  for (const piece of glasses) {
    const spec = piece.glass_spec ?? "—";
    const sku = piece.article_sku ?? "—";
    const thickness = piece.thickness_net_mm ?? "—";
    const key = `${spec}|${sku}|${thickness}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        spec,
        sku,
        thickness,
        pieces: [],
        qty: 0,
        areaScaled: 0n,
        weightScaled: 0n,
        weightUnknown: false,
      };
      groups.set(key, group);
    }
    const entry = polishByKey.get(polishKey(piece.bay_id, piece.leaf_id));
    group.pieces.push({ piece, edges: edgeLabel(entry?.edges) });
    group.qty += 1;
    group.areaScaled += scaled(piece.area_m2);
    if (piece.weight_kg == null) {
      group.weightUnknown = true;
    } else {
      group.weightScaled += scaled(piece.weight_kg);
    }
  }
  const grouped = [...groups.values()];
  const totalQty = grouped.reduce((sum, group) => sum + group.qty, 0);
  const totalArea = grouped.reduce((sum, group) => sum + group.areaScaled, 0n);
  const totalWeight = grouped.reduce((sum, group) => sum + group.weightScaled, 0n);
  const totalUnknown = grouped.some((group) => group.weightUnknown);

  return (
    <section className="production-glass" aria-label={t("production.glassSummaryTitle")}>
      <header className="production-optimize-head">
        <h3>{t("production.glassSummaryTitle")}</h3>
        <button type="button" onClick={() => onExport(grouped)}>
          {t("production.glassExport")}
        </button>
      </header>
      {grouped.length ? (
        <table className="production-plan">
          <thead>
            <tr>
              <th>{t("production.glassColSpec")}</th>
              <th>{t("production.glassColSku")}</th>
              <th>{t("production.glassColThickness")}</th>
              <th>{t("production.glassColDims")}</th>
              <th>{t("production.glassColQty")}</th>
              <th>{t("production.glassColArea")}</th>
              <th>{t("production.glassColWeight")}</th>
              <th>{t("production.glassColPolish")}</th>
            </tr>
          </thead>
          <tbody>
            {grouped.map((group) => {
              const rows = sizeRows(group);
              return rows.map((row, rowIndex) => (
                <tr key={`${group.spec}-${group.sku}-${row.dims}-${row.edges}`}>
                  {rowIndex === 0 ? <td rowSpan={rows.length}>{group.spec}</td> : null}
                  {rowIndex === 0 ? <td rowSpan={rows.length}>{group.sku}</td> : null}
                  {rowIndex === 0 ? <td rowSpan={rows.length}>{group.thickness} mm</td> : null}
                  <td>{row.dims} mm</td>
                  <td>{row.count * quantity}</td>
                  {rowIndex === 0 ? (
                    <td rowSpan={rows.length}>
                      {fmtScaled(group.areaScaled * BigInt(quantity), 4)} m²
                    </td>
                  ) : null}
                  {rowIndex === 0 ? (
                    <td rowSpan={rows.length}>
                      {group.weightUnknown
                        ? t("production.glassWeightUnknown")
                        : `${fmtScaled(group.weightScaled * BigInt(quantity), 2)} kg`}
                    </td>
                  ) : null}
                  <td>{row.edges}</td>
                </tr>
              ));
            })}
            <tr className="production-glass-total">
              <td colSpan={4}>{t("production.glassTotals")}</td>
              <td>{totalQty * quantity}</td>
              <td>{fmtScaled(totalArea * BigInt(quantity), 4)} m²</td>
              <td>
                {totalUnknown
                  ? t("production.glassWeightUnknown")
                  : `${fmtScaled(totalWeight * BigInt(quantity), 2)} kg`}
              </td>
              <td />
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="production-optimize-empty">{t("production.glassEmpty")}</p>
      )}
    </section>
  );
}
