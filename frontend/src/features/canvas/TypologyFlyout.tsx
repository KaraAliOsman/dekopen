import { useMemo, useState } from "react";

import type { OpeningOption, ProductIssue } from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import type { MemberGeometry } from "./members";
import type { OpeningChoice } from "./intentEditing";
import { intentBays } from "./intentEditing";
import { openingOptionAdmitted } from "./openings";
import { ProductFrontSvg } from "./ProductFrontSvg";
import type { ProductJson } from "./productEditing";
import { STARTER_DEFINITIONS, starterNominalSize, type StarterDefinition } from "./designLibrary";

const NO_ISSUES: ProductIssue[] = [];
const NOOP = () => {};

export function StarterThumb({
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

/** Starter groups for the rail flyout — the library's recipes grouped the
 * way a quoter asks for them. Order inside a group is the library's. */
const STARTER_GROUPS: readonly { key: string; titleKey: TranslationKey; members: string[] }[] = [
  {
    key: "windows",
    titleKey: "assembly.starterGroupWindows",
    members: ["fixed", "sash", "twoSash", "awning", "awningBand"],
  },
  {
    key: "sliding",
    titleKey: "assembly.starterGroupSliding",
    members: ["sliding2", "sliding3", "slidingFixed"],
  },
  {
    key: "doors",
    titleKey: "assembly.starterGroupDoors",
    members: ["doorSide"],
  },
  {
    key: "assemblies",
    titleKey: "assembly.starterGroupAssemblies",
    members: ["coupled", "bow3", "bow5"],
  },
  {
    key: "specials",
    titleKey: "assembly.starterGroupSpecials",
    members: ["trapezoid", "arch", "frameless"],
  },
];

/** A starter is offered only when every opening its bays would draw is
 * admitted by the selected system — a window recipe must never propose a
 * corredera the catalog can't build. */
export function starterCompatible(
  definition: StarterDefinition,
  openingOptions: readonly OpeningOption[] | undefined,
): boolean {
  const { widthMm, heightMm } = starterNominalSize(definition.key);
  const product = definition.build(widthMm, heightMm);
  const bays = product.assembly.modules.flatMap((module) => intentBays(module.tree));
  return bays.every((bay) =>
    openingOptionAdmitted((bay.opening_type ?? "FIXED") as OpeningChoice, openingOptions),
  );
}

/** Typology flyout off the tool rail: grouped recipe cards drawn by the
 * same renderer the canvas uses, filtered to the chosen system's declared
 * openings, with the search box retained. */
export function TypologyFlyout({
  members,
  openingOptions,
  disabled,
  onPick,
}: {
  members: MemberGeometry;
  openingOptions: readonly OpeningOption[] | undefined;
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
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const admitted = previews.filter(({ definition }) => {
      if (!starterCompatible(definition, openingOptions)) return false;
      if (!needle) return true;
      return `${t(definition.titleKey)} ${t(definition.hintKey)}`.toLowerCase().includes(needle);
    });
    return STARTER_GROUPS.map((group) => ({
      ...group,
      starters: admitted.filter(({ definition }) => group.members.includes(definition.key)),
    })).filter((group) => group.starters.length > 0);
  }, [previews, openingOptions, query]);

  return (
    <div className="typology-flyout" role="dialog" aria-label={t("assembly.starterLibrary")}>
      <label className="starter-search">
        <input
          type="search"
          value={query}
          placeholder={t("assembly.starterSearch")}
          aria-label={t("assembly.starterSearch")}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {groups.length === 0 ? (
        <p className="starter-empty" role="status">
          {t("assembly.starterNoMatch")}
        </p>
      ) : (
        <div className="typology-flyout__groups">
          {groups.map((group) => (
            <section key={group.key} className="typology-group">
              <h5 className="typology-group__title">{t(group.titleKey)}</h5>
              <div className="starter-gallery" role="list" aria-label={t(group.titleKey)}>
                {group.starters.map(({ definition, product }) => (
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
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
