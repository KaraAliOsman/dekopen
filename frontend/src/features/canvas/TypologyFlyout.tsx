import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { OpeningOption, ProductIssue } from "../../api/generated/models";
import { engineSystems, projectDesignOptions } from "../../api/generated/dekopen";
import { t, type TranslationKey } from "../../i18n/es-CL";
import type { MemberGeometry } from "./members";
import type { OpeningChoice } from "./intentEditing";
import { bayLeafTraces, intentBays, nodeSpecKey } from "./intentEditing";
import { openingOptionAdmitted, openingSpecKeyAdmitted } from "./openings";
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
  {
    key: "advanced",
    titleKey: "assembly.starterGroupAdvanced",
    members: ["hst", "psk", "foldable", "pivot", "guillotina", "slidingDoor"],
  },
];

/** A starter is offered only when every opening its bays would draw is
 * admitted by the selected system — a window recipe must never propose a
 * corredera the catalog can't build. Spec bays (D08) compare their exact
 * emitted composition key; legacy enums resolve through the grid map. */
export function starterCompatible(
  definition: StarterDefinition,
  openingOptions: readonly OpeningOption[] | undefined,
): boolean {
  const { widthMm, heightMm } = starterNominalSize(definition.key);
  const product = definition.build(widthMm, heightMm);
  return product.assembly.modules.every((module) =>
    intentBays(module.tree).every((bay) => {
      if (bayLeafTraces(bay)[0]?.opening) {
        return openingSpecKeyAdmitted(nodeSpecKey(module.tree, bay), openingOptions);
      }
      return openingOptionAdmitted((bay.opening_type ?? "FIXED") as OpeningChoice, openingOptions);
    }),
  );
}

/** §8: which catalog systems admit a starter the active series can't —
 * read the opening_options each system's design options emit and answer
 * with names, never guesses. */
export function starterAdmittingSystems(
  definition: StarterDefinition,
  systems: readonly { name: string; openingOptions: readonly OpeningOption[] | undefined }[],
): string[] {
  return systems
    .filter((system) => starterCompatible(definition, system.openingOptions))
    .map((system) => system.name);
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
  const { admitted, blocked } = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = previews.filter(({ definition }) => {
      if (!needle) return true;
      return `${t(definition.titleKey)} ${t(definition.hintKey)}`.toLowerCase().includes(needle);
    });
    return {
      admitted: matches.filter(({ definition }) => starterCompatible(definition, openingOptions)),
      blocked: matches.filter(({ definition }) => !starterCompatible(definition, openingOptions)),
    };
  }, [previews, openingOptions, query]);
  const groups = useMemo(
    () =>
      STARTER_GROUPS.map((group) => ({
        ...group,
        starters: admitted.filter(({ definition }) => group.members.includes(definition.key)),
      })).filter((group) => group.starters.length > 0),
    [admitted],
  );
  // §8 — lazy: the blocked section only asks every catalog series for its
  // declared options when the user opens the disclosure. Names come from
  // the catalog itself, so "la admiten" never invents a system.
  const [blockedOpen, setBlockedOpen] = useState(false);
  const systemsOptions = useQuery({
    queryKey: ["typology-flyout-system-options"],
    enabled: blockedOpen && blocked.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
    queryFn: async () => {
      const listResponse = await engineSystems();
      if (listResponse.status !== 200) throw new Error("load");
      const rows = await Promise.all(
        listResponse.data.systems.map(async (system) => {
          const optionsResponse = await projectDesignOptions(system.id);
          return {
            name: system.name,
            openingOptions:
              optionsResponse.status === 200 ? (optionsResponse.data.opening_options ?? []) : [],
          };
        }),
      );
      return rows;
    },
  });

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
      {groups.length === 0 && blocked.length === 0 ? (
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
          {blocked.length > 0 && (
            <section className="typology-group typology-group--blocked">
              <details
                className="typology-blocked"
                onToggle={(event) => setBlockedOpen(event.currentTarget.open)}
              >
                <summary className="typology-blocked__summary">
                  {t("assembly.starterBlockedTitle")} ({blocked.length})
                </summary>
                <div className="starter-gallery" role="list">
                  {blocked.map(({ definition, product }) => (
                    <div
                      key={definition.key}
                      role="listitem"
                      className="starter-card-wrap starter-card-wrap--blocked"
                    >
                      <div className="starter-card starter-card--blocked" aria-disabled="true">
                        <span className="starter-thumb">
                          <StarterThumb product={product} members={members} />
                        </span>
                        <span className="starter-card-title">{t(definition.titleKey)}</span>
                        <span className="starter-card-hint">{t(definition.hintKey)}</span>
                        <span className="starter-card-cause">
                          {t("assembly.starterBlockedCause")}
                        </span>
                        <span className="starter-card-admitting">
                          {systemsOptions.isPending && blockedOpen
                            ? t("assembly.starterBlockedLoading")
                            : systemsOptions.isError
                              ? t("assembly.starterBlockedError")
                              : systemsOptions.data
                                ? (() => {
                                    const names = starterAdmittingSystems(
                                      definition,
                                      systemsOptions.data,
                                    );
                                    return names.length > 0
                                      ? `${t("assembly.starterBlockedAdmitting")} ${names.join(", ")}`
                                      : t("assembly.starterBlockedNone");
                                  })()
                                : null}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
