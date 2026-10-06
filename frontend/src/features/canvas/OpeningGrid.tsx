import type { OpeningOption } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { OpeningGlyph } from "./ProductFrontSvg";
import { OPTION_SPEC_KEY, type OpeningChoice } from "./intentEditing";
import { OPENING_OPTIONS, openingOptionAdmitted } from "./openings";

/** The shared opening selector: catalog-filtered choices with their real
 * Spanish names and the drawing grammar's glyph — used by the module and
 * bay inspectors and by the double-click canvas selector. Only what the
 * system's `opening_options` admits is rendered (never a disabled "why
 * not" the catalog can't honor). */
export function OpeningGrid({
  openingOptions,
  /** Spec key the current bay/module emits — marks the active choice. */
  activeKey,
  /** Legacy enum the node carries, when it doesn't match a spec key. */
  activeChoice = "",
  busy,
  /** DOOR_ENTRY only makes sense on the module's top bay — non-top bays
   * keep the choice visible but refused (the door rule is geometry, not
   * catalog). */
  doorBlocked = false,
  onPick,
}: {
  openingOptions: readonly OpeningOption[] | undefined;
  activeKey: string;
  activeChoice?: string;
  busy: boolean;
  doorBlocked?: boolean;
  onPick(choice: OpeningChoice): void;
}): JSX.Element {
  return (
    <div className="opening-grid" role="group" aria-label={t("assembly.opening")}>
      {OPENING_OPTIONS.filter(([value]) => openingOptionAdmitted(value, openingOptions)).map(
        ([value, labelKey]) => {
          const isActive = OPTION_SPEC_KEY[value] === activeKey || value === activeChoice;
          const glyphKey = OPTION_SPEC_KEY[value] === "SLIDE" ? value : OPTION_SPEC_KEY[value];
          const blocked = doorBlocked && value === "DOOR_ENTRY";
          return (
            <button
              key={value}
              type="button"
              className={`opening-choice${isActive ? " is-active" : ""}`}
              data-opening={value}
              title={blocked ? t("assembly.doorTopOnly") : t(labelKey)}
              aria-label={t(labelKey)}
              aria-pressed={isActive}
              disabled={busy || blocked}
              onClick={() => onPick(value)}
            >
              <svg viewBox="0 0 100 100" aria-hidden="true">
                <rect className="opening-choice__frame" x={4} y={4} width={92} height={92} />
                <OpeningGlyph
                  opening={OPTION_SPEC_KEY[value] === "SLIDE" ? value : glyphKey}
                  x={4}
                  y={4}
                  w={92}
                  h={92}
                />
              </svg>
              <span className="opening-choice__name">{t(labelKey)}</span>
            </button>
          );
        },
      )}
    </div>
  );
}
