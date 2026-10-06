import type { ProductIssue } from "../../api/generated/models/productIssue";
import { ProductFrontContent, frontLayout } from "../canvas/ProductFrontSvg";
import type { ProductJson } from "../canvas/productEditing";
import { THUMB_MEMBERS } from "../projects/PositionThumb";

const NO_ISSUES: ProductIssue[] = [];
const NOOP = () => {};

/** Dibujable = cada módulo trae su árbol paramétrico (productos mínimos de
 * test o snapshots viejos pueden carecer de él — la tarjeta omite el dibujo
 * antes que romper el hilo). */
export function isDrawableProduct(product: ProductJson | null | undefined): boolean {
  return Boolean(
    product?.assembly?.modules?.every(
      (module) => module && typeof module === "object" && module.tree != null,
    ),
  );
}

/** §P17 — la vista previa dibujada: el mismo renderer del canvas (misma
 * geometría, mismo vocabulario visual) sobre un producto — «antes» y
 * «después» de una propuesta se dibujan con la verdad del modelo, nunca
 * con una ilustración libre. */
export function ProductPreviewFigure({
  product,
  label,
  height = 120,
}: {
  product: ProductJson;
  label: string;
  height?: number;
}) {
  const { totalW, height: layoutHeight, lift, dip, leftOver, rightOver } = frontLayout(product);
  const pad = 8;
  const viewBox = [
    -pad - leftOver,
    -pad,
    totalW + leftOver + rightOver + pad * 2,
    layoutHeight + lift + dip + pad * 2,
  ].join(" ");
  return (
    <figure className="ops-card__preview">
      <svg
        className="ops-card__svg"
        style={{ height }}
        viewBox={viewBox}
        role="img"
        aria-label={label}
      >
        <ProductFrontContent
          product={product}
          members={THUMB_MEMBERS}
          selectedId={null}
          issues={NO_ISSUES}
          disabled
          preview
          onSelectModule={NOOP}
          onAddUnit={NOOP}
          onCommitModuleWidth={NOOP}
          onCommitTotalWidth={NOOP}
          onCommitHeight={NOOP}
        />
      </svg>
      <figcaption>{label}</figcaption>
    </figure>
  );
}
