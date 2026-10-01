import { useMemo, useState } from "react";

import type { ProductIssue } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { STARTER_DEFINITIONS, starterNominalSize, type StarterDefinition } from "./designLibrary";
import type { MemberGeometry } from "./members";
import { ProductFrontSvg } from "./ProductFrontSvg";
import type { ProductJson } from "./productEditing";

const NO_ISSUES: ProductIssue[] = [];
const NOOP = () => {};

function StarterThumb({
  product,
  members,
}: {
  product: ProductJson;
  members: MemberGeometry;
}): JSX.Element {
  return (
    <ProductFrontSvg
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
  );
}

/** Design library: starter cards previewed through the same front-elevation
 * renderer as the workspace, so a template reads exactly like the product it
 * creates — including catalog face widths and material surfaces once a series
 * is selected. Cards are creation recipes, not product types. */
export function StarterGallery({
  members,
  disabled,
  onPick,
}: {
  members: MemberGeometry;
  disabled: boolean;
  onPick(definition: StarterDefinition): void;
}): JSX.Element {
  const previews = useMemo(
    () =>
      STARTER_DEFINITIONS.map((definition) => {
        const { widthMm, heightMm } = starterNominalSize(definition.key);
        return { definition, product: definition.build(widthMm, heightMm) };
      }),
    [],
  );
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return previews;
    return previews.filter(({ definition }) =>
      `${t(definition.titleKey)} ${t(definition.hintKey)}`.toLowerCase().includes(needle),
    );
  }, [previews, query]);
  return (
    <div className="starter-gallery-wrap">
      <label className="starter-search">
        <input
          type="search"
          value={query}
          placeholder={t("assembly.starterSearch")}
          aria-label={t("assembly.starterSearch")}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {filtered.length === 0 ? (
        <p className="starter-empty" role="status">
          {t("assembly.starterNoMatch")}
        </p>
      ) : (
        <div className="starter-gallery" role="list" aria-label={t("assembly.starterLibrary")}>
          {filtered.map(({ definition, product }) => (
            <div key={definition.key} role="listitem" className="starter-card-wrap">
              <button
                type="button"
                className="starter-card"
                disabled={disabled}
                onClick={() => onPick(definition)}
              >
                <span className="starter-thumb">
                  <StarterThumb product={product} members={members} />
                </span>
                <span className="starter-card-title">{t(definition.titleKey)}</span>
                <span className="starter-card-hint">{t(definition.hintKey)}</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
