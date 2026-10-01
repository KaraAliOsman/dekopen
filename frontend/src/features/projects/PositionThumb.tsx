import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import type { PositionDesign, ProductIssue } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import type { IntentNode } from "../canvas/intentEditing";
import { resolveMembers, type MemberGeometry } from "../canvas/members";
import { isProductModel, wrapTreeAsProduct, type ProductJson } from "../canvas/productEditing";
import { frontLayout, ProductFrontContent } from "../canvas/ProductFrontSvg";
import { webglAvailable } from "../canvas/webglAvailable";

// three.js stays behind the dynamic boundary — the studio renderer only
// loads when a card actually renders it (lazy fetches on first render).
const LazyStudioImage = lazy(() =>
  import("../canvas/renderStudio").then((mod) => ({ default: mod.StudioImage })),
);

const NO_ISSUES: ProductIssue[] = [];
const NOOP = () => {};

/** Neutral PVC-60 member geometry — the thumbnail shows real bay layout and
 * opening glyphs; catalog face widths only exist inside the editor. */
export const THUMB_MEMBERS = resolveMembers(undefined);

function designProduct(design: PositionDesign): ProductJson {
  const tree = design.parametric_tree;
  if (isProductModel(tree)) return tree;
  return wrapTreeAsProduct(tree as IntentNode, design.nominal_width_mm, design.nominal_height_mm);
}

/** WebGL thumb renders are the expensive part of a position grid — only
 * pay for them once the card actually scrolls into view. Off-screen cards
 * keep the cheap elevation until then. */
function useVisible<T extends HTMLElement>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || visible || typeof IntersectionObserver === "undefined") {
      if (!visible && typeof IntersectionObserver === "undefined") setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);
  return [ref, visible];
}

/** Live front-elevation thumbnail for a saved position: classic trees are
 * wrapped as a one-module product so both storage shapes render identically.
 * The tight viewBox crops the dimension chains — only the product reads. */
export function PositionThumb({
  design,
  variant = "elevation",
  members = THUMB_MEMBERS,
}: {
  design: PositionDesign;
  /** "studio" renders the §05 commercial view — the premium visual for
   * project cards; "elevation" keeps the technical line drawing used
   * where changes are compared side by side. */
  variant?: "elevation" | "studio";
  /** Member geometry+material override — callers that know the sealed finish
   * (portal) pass a re-skinned set so the render matches the quoted color. */
  members?: MemberGeometry;
}): JSX.Element {
  const product = useMemo(() => designProduct(design), [design]);
  const [hostRef, visible] = useVisible<HTMLDivElement>();
  // Grid cards re-render on every parent pass — the layout must not.
  const { totalW, height, lift, dip, leftOver, rightOver } = useMemo(
    () => frontLayout(product),
    [product],
  );
  // No WebGL → the technical elevation keeps rendering; the studio card
  // would otherwise degrade to an empty placeholder.
  const pad = 8;
  const elevation = (
    <svg
      className="position-thumb"
      viewBox={`${-pad - leftOver} ${-pad} ${totalW + leftOver + rightOver + pad * 2} ${height + lift + dip + pad * 2}`}
      role="img"
      aria-label={t("projects.positionThumb")}
    >
      <ProductFrontContent
        product={product}
        members={members}
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
  );
  if (variant === "studio" && webglAvailable()) {
    return (
      <div ref={hostRef} className="position-thumb-host">
        {visible ? (
          <Suspense fallback={elevation}>
            <LazyStudioImage
              product={product}
              members={members}
              options={{ width: 360, height: 300 }}
              alt={t("projects.positionThumb")}
              className="position-thumb"
            />
          </Suspense>
        ) : (
          elevation
        )}
      </div>
    );
  }
  return elevation;
}
