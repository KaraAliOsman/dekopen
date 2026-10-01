import type { DesignOptions, ProductIssue } from "../../api/generated/models";
import type { TranslationKey } from "../../i18n/es-CL";
import type { IntentNode, Opening } from "./intentEditing";
import type { ProductJson } from "./productEditing";
import type { MemberGeometry } from "./members";

/** A row in the product object tree — human names only, never raw ids/enums. */
export interface TreeNode {
  id: string;
  label: string;
  detail: string | null;
  kind:
    "root" | "module" | "bay" | "member" | "glazing" | "handle" | "mullion" | "coupler" | "panel";
  severity: "error" | "warning" | null;
  /** Canvas selection target (module or coupling id); null = structural row. */
  selectId: string | null;
  /** Accessible name when the visible label alone is ambiguous (e.g. a bay
   * whose opening name collides with the opening-type choice buttons). */
  ariaLabel?: string;
  children: TreeNode[];
}

const LEAF_KIND: Record<Opening, TranslationKey> = {
  FIXED: "intent.fixed",
  TURN_LEFT: "intent.turnLeft",
  TURN_RIGHT: "intent.turnRight",
  TILT_TURN_LEFT: "intent.tiltLeft",
  TILT_TURN_RIGHT: "intent.tiltRight",
  AWNING: "intent.awning",
  SLIDING_2L: "intent.sliding",
  SLIDING_3L: "intent.sliding3",
  SLIDING_4L: "intent.sliding4",
  SLIDING: "intent.slidingLayout",
  DOOR_ENTRY: "intent.door",
};

function severityFor(issues: ProductIssue[], target: string): "error" | "warning" | null {
  let worst: "error" | "warning" | null = null;
  for (const issue of issues) {
    if (issue.target !== target) continue;
    if (issue.severity === "error") return "error";
    worst = "warning";
  }
  return worst;
}

function bayChildren(
  node: IntentNode,
  moduleId: string,
  members: MemberGeometry,
  t: (key: TranslationKey) => string,
  glassNames: Map<string, string>,
): TreeNode[] {
  const rows: TreeNode[] = [];
  const opening = node.opening_type ?? "FIXED";
  const operable = opening !== "FIXED";
  if (operable) {
    rows.push({
      id: `${moduleId}/${node.id}/sash`,
      label: t("tree.sash"),
      detail: members.sash.name ?? members.sash.sku,
      kind: "member",
      severity: null,
      selectId: `${moduleId}/${node.id}`,
      children: [],
    });
    rows.push({
      id: `${moduleId}/${node.id}/handle`,
      label: t("tree.handle"),
      detail: node.handle_height_mm ? `${node.handle_height_mm} mm` : null,
      kind: "handle",
      severity: null,
      selectId: `${moduleId}/${node.id}`,
      children: [],
    });
  }
  if (node.panel_article_sku) {
    rows.push({
      id: `${moduleId}/${node.id}/panel`,
      label: t("tree.panel"),
      detail: node.panel_article_sku,
      kind: "panel",
      severity: null,
      selectId: `${moduleId}/${node.id}`,
      children: [],
    });
  } else {
    const detail = [
      node.glass_thickness_mm ? `${node.glass_thickness_mm} mm` : null,
      // Prefer the catalog spec text over the raw SKU — "VIDRIO-BASE" is a
      // code, not a label a designer should read.
      node.glass_article_sku
        ? (glassNames.get(node.glass_article_sku) ?? node.glass_spec ?? null)
        : (node.glass_spec ?? null),
    ]
      .filter(Boolean)
      .join(" · ");
    rows.push({
      id: `${moduleId}/${node.id}/glass`,
      label: t("tree.glass"),
      detail: detail || null,
      kind: "glazing",
      severity: null,
      selectId: `${moduleId}/${node.id}`,
      children: [],
    });
  }
  return rows;
}

interface BayContext {
  moduleLabel: string;
  bayCounter: { value: number };
  /** glass SKU → human spec text ("Vidrio 24mm" instead of "VIDRIO-BASE"). */
  glassNames: Map<string, string>;
}

function intentRows(
  node: IntentNode,
  moduleId: string,
  members: MemberGeometry,
  t: (key: TranslationKey) => string,
  context: BayContext,
): TreeNode[] {
  if (node.type === "BAY") {
    const opening = node.opening_type ?? "FIXED";
    const label = t(LEAF_KIND[opening]);
    context.bayCounter.value += 1;
    return [
      {
        id: `${moduleId}/${node.id}`,
        label,
        detail: null,
        kind: "bay",
        severity: null,
        selectId: `${moduleId}/${node.id}`,
        ariaLabel: `${label} · ${t("tree.bay")} ${context.bayCounter.value} · ${context.moduleLabel}`,
        children: bayChildren(node, moduleId, members, t, context.glassNames),
      },
    ];
  }
  if (node.type === "SPLIT_V" || node.type === "SPLIT_H") {
    return [
      {
        id: `${moduleId}/${node.id}`,
        label: node.type === "SPLIT_V" ? t("tree.mullionV") : t("tree.mullionH"),
        detail:
          (node.type === "SPLIT_V" ? members.mullionV : members.mullionH)?.name ??
          node.mullion_profile_sku ??
          null,
        kind: "mullion",
        severity: null,
        selectId: `${moduleId}/${node.id}`,
        children: (node.children ?? []).flatMap((child) =>
          intentRows(child, moduleId, members, t, context),
        ),
      },
    ];
  }
  return (node.children ?? []).flatMap((child) => intentRows(child, moduleId, members, t, context));
}

/** Modules interleaved with their couplings — the tree reads like the
 * assembly walks left to right. */
export function buildObjectTree(
  product: ProductJson,
  members: MemberGeometry,
  issues: ProductIssue[],
  t: (key: TranslationKey) => string,
  options?: DesignOptions,
): TreeNode {
  const { modules, couplings } = product.assembly;
  const glassNames = new Map(
    (options?.glass_specs ?? [])
      .filter((choice) => choice.spec)
      .map((choice) => [choice.sku, choice.spec as string]),
  );
  const couplerNames = new Map(
    (options?.coupler_profiles ?? []).map((choice) => [choice.sku, choice.name]),
  );
  const children: TreeNode[] = [];
  modules.forEach((module, index) => {
    const width = Number(module.width_mm);
    const height = Number(module.height_mm);
    children.push({
      id: `module:${module.id}`,
      label: `${t("tree.module")} ${index + 1}`,
      detail: `${width} × ${height} mm`,
      kind: "module",
      severity: severityFor(issues, `module:${module.id}`),
      selectId: module.id,
      children: [
        {
          id: `${module.id}/frame`,
          label: t("tree.frame"),
          detail: members.frame.name ?? members.frame.sku,
          kind: "member",
          severity: null,
          selectId: module.id,
          children: [],
        },
        ...intentRows(module.tree, module.id, members, t, {
          moduleLabel: `${t("tree.module")} ${index + 1}`,
          bayCounter: { value: 0 },
          glassNames,
        }),
      ],
    });
    const coupling = couplings[index];
    if (coupling) {
      children.push({
        id: `coupling:${coupling.id}`,
        label: t("tree.coupler"),
        detail: `${couplerNames.get(coupling.coupler_profile_sku ?? "") ?? coupling.coupler_profile_sku ?? "?"} · ${coupling.angle_deg}°`,
        kind: "coupler",
        severity: severityFor(issues, `coupling:${coupling.id}`),
        selectId: coupling.id,
        children: [],
      });
    }
  });
  const totalW = modules.reduce((sum, module) => sum + Number(module.width_mm), 0);
  const height = Math.max(...modules.map((module) => Number(module.height_mm)));
  return {
    id: "root",
    label: t("tree.product"),
    detail:
      `${totalW} × ${height} mm · ${modules.length} ` +
      t(modules.length === 1 ? "tree.unitsOne" : "tree.units"),
    kind: "root",
    severity: null,
    selectId: null,
    children,
  };
}
