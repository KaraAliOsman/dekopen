import { fmtMm } from "../../format";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  engineSystems,
  positionsCreate,
  positionsRetrieve,
  positionsUpdate,
  projectDesignOptions,
} from "../../api/generated/dekopen";

import type {
  EngineAssemblyCalculateResponse,
  EngineCalculateResponse,
  PositionDesignRequest,
  PositionResponse,
} from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { ApiError } from "../../api/apiMutator";
import { UnsavedChangesGuard } from "../../app/UnsavedChangesGuard";
import { useShellLeaf } from "../../app/shellLeaf";
import { t, tDynamic, tOptional } from "../../i18n/es-CL";
import { DeniedState } from "../../ui";
import { type CanvasDesignInputs, useCanvasStore } from "../canvas/canvasStore";
import { useProject } from "./useProject";
import { AssemblyEditor, issueText } from "../canvas/AssemblyEditor";
import { useAssistantSurface } from "../assistant/assistantContext";
import type { IntentNode, Opening } from "../canvas/intentEditing";
import {
  starterContextSize,
  starterNominalSize,
  type StarterDefinition,
} from "../canvas/designLibrary";
import { resolveMembers } from "../canvas/members";
import {
  clearPositionDraft,
  positionDraftKey,
  type PositionDraft,
  readPositionDraft,
  writePositionDraft,
} from "./positionDraft";
import { StarterGallery } from "../canvas/StarterGallery";
import {
  elevationEnvelopeMm,
  isProductModel,
  isSingleUnit,
  wrapTreeAsProduct,
  type ProductJson,
} from "../canvas/productEditing";

import "./projects.css";

export function ProjectPositionEditor(): JSX.Element {
  const { id = "", posId = "" } = useParams();
  const [query] = useSearchParams();
  const copyId = posId ? "" : (query.get("copy") ?? "");
  const preferredSystem = posId || copyId ? null : query.get("system");
  const org = useAuthSession().me?.active_organization;
  const canEdit = Boolean(org && ["OWNER", "ESTIMATOR"].includes(org.role));
  // The editor must not mount on a closed revision — the backend's editable()
  // gate would 409 every save, so check BEFORE the canvas store and dirty
  // tracking initialize (review: the «Nuevo vano» dead-end on quoted deals).
  const projectQuery = useProject(canEdit && id ? id : null);
  if (!canEdit) return <DeniedState reason={t("projects.denied")} />;
  const project = projectQuery.data;
  // Mirrors backend editable(): a closed revision is status≠DRAFT, a sealed
  // version row for current_revision, or an applied pricing authority.
  const locked = Boolean(
    project &&
    (project.status !== "DRAFT" ||
      project.versions?.some((version) => version.revision_code === project.current_revision) ||
      project.current_pricing_operation_id),
  );
  if (locked) {
    return (
      <div className="ui-empty ui-empty--denied">
        <svg className="ui-empty__glyph" aria-hidden="true" viewBox="0 0 16 16">
          <rect x="3" y="7" width="10" height="7" rx="1.5" />
          <path d="M5.5 7V5.5a2.5 2.5 0 0 1 5 0V7" />
        </svg>
        <p className="ui-empty__title">{t("projects.editorLockedTitle")}</p>
        <p className="ui-empty__body">{t("projects.editorLockedBody")}</p>
        <div className="ui-empty__action">
          <Link className="ui-button" to={`/projects/${id}`}>
            {t("projects.editorLockedBack")}
          </Link>
        </div>
      </div>
    );
  }
  return (
    <PositionWorkspace
      key={`${org!.id}:${id}:${posId}:${copyId}`}
      orgId={org!.id}
      preferredSystem={preferredSystem}
      projectId={id}
      positionId={posId}
      copyId={copyId}
    />
  );
}

function starterTree(opening: Opening): IntentNode {
  return { id: crypto.randomUUID(), type: "BAY", opening_type: opening };
}

function initial(): CanvasDesignInputs {
  const product = wrapTreeAsProduct(starterTree("FIXED"), "1000.00", "1000.00");
  return {
    systemId: null,
    nominalWidthMm: "1000.00",
    nominalHeightMm: "1000.00",
    color: "WHITE",
    parametricTree: product.assembly.modules[0]?.tree ?? starterTree("FIXED"),
    product,
  };
}

/** Fill catalog-driven values that are uniquely determined: a coupling without
 * a coupler gets the catalog's only coupler; splits without a mullion get the
 * catalog's only mullion of that direction; bays without glazing get the
 * catalog's only thickness (the spec defaults to the same monolithic value).
 * Ambiguity stays unresolved — the choice is surfaced in the inspector,
 * never guessed. */
function resolveDefaults(
  product: ProductJson,
  couplerSkus: string[],
  mullionSkus: { SPLIT_V?: string; SPLIT_H?: string },
  glassThicknessMm?: string,
  panelSku?: string,
): ProductJson {
  let next = product;
  if (couplerSkus.length === 1) {
    const sku = couplerSkus[0]!;
    for (const coupling of next.assembly.couplings) {
      if (coupling.coupler_profile_sku === null) {
        next = {
          ...next,
          assembly: {
            ...next.assembly,
            couplings: next.assembly.couplings.map((item) =>
              item.id === coupling.id ? { ...item, coupler_profile_sku: sku } : item,
            ),
          },
        };
      }
    }
  }
  const needsFill = (node: IntentNode): boolean => {
    const missingMullion =
      (node.type === "SPLIT_V" || node.type === "SPLIT_H") &&
      !node.mullion_profile_sku &&
      mullionSkus[node.type] !== undefined;
    const missingGlass =
      node.type === "BAY" &&
      glassThicknessMm !== undefined &&
      (!node.glass_thickness_mm || !node.glass_spec);
    const missingPanel =
      node.type === "BAY" &&
      node.opening_type === "DOOR_ENTRY" &&
      !node.panel_article_sku &&
      panelSku !== undefined;
    // A door without declared handedness cannot freeze — manufacturing
    // refuses to guess the hinge side, so autofill declares the default.
    const missingHandedness =
      node.type === "BAY" && node.opening_type === "DOOR_ENTRY" && node.door_handedness == null;
    return (
      missingMullion ||
      missingGlass ||
      missingPanel ||
      missingHandedness ||
      (node.children?.some(needsFill) ?? false)
    );
  };
  const fill = (node: IntentNode): IntentNode => {
    let updated = node;
    if (
      (node.type === "SPLIT_V" || node.type === "SPLIT_H") &&
      !node.mullion_profile_sku &&
      mullionSkus[node.type] !== undefined
    ) {
      updated = { ...updated, mullion_profile_sku: mullionSkus[node.type] };
    }
    if (updated.type === "BAY" && glassThicknessMm !== undefined) {
      if (!updated.glass_thickness_mm)
        updated = { ...updated, glass_thickness_mm: glassThicknessMm };
      if (!updated.glass_spec) updated = { ...updated, glass_spec: glassThicknessMm };
    }
    if (updated.type === "BAY" && updated.opening_type === "DOOR_ENTRY" && panelSku !== undefined) {
      if (!updated.panel_article_sku) updated = { ...updated, panel_article_sku: panelSku };
    }
    if (
      updated.type === "BAY" &&
      updated.opening_type === "DOOR_ENTRY" &&
      updated.door_handedness == null
    ) {
      updated = { ...updated, door_handedness: "LEFT" };
    }
    return { ...updated, children: node.children?.map(fill) };
  };
  if (next.assembly.modules.some((module) => needsFill(module.tree))) {
    next = {
      ...next,
      assembly: {
        ...next.assembly,
        modules: next.assembly.modules.map((module) => ({
          ...module,
          tree: fill(module.tree),
        })),
      },
    };
  }
  return next;
}

/** The design object that save() would send — used both by save and by the
 * dirty baseline, so they can never disagree about what "unchanged" means.
 * The finish choice is validated against the series' declared colors — never
 * a hardcoded white, and a catalog option the engine can't map stays
 * unsaveable instead of throwing. */
function designPayload(
  inputs: CanvasDesignInputs,
  allowedColors: string[],
): PositionDesignRequest | null {
  const product = inputs.product;
  // The picker's options come from the system's declared finishes — a color
  // outside that set stays displayed and selectable but unsaveable, never
  // silently coerced.
  const color = allowedColors.includes(inputs.color) ? inputs.color : null;
  if (product === null || !inputs.systemId || color === null) return null;
  const single = isSingleUnit(product) ? product.assembly.modules[0] : undefined;
  return single !== undefined
    ? {
        system_id: inputs.systemId,
        nominal_width_mm: single.width_mm,
        nominal_height_mm: single.height_mm,
        color,
        parametric_tree: single.tree,
      }
    : {
        system_id: inputs.systemId,
        nominal_width_mm: elevationEnvelopeMm(product).width.toFixed(2),
        nominal_height_mm: elevationEnvelopeMm(product).height.toFixed(2),
        color,
        parametric_tree: product,
      };
}

/** The unsaved-changes identity — the live inputs themselves, not the
 * save payload: a canvas design with no system picked yet produces no
 * payload at all, and comparing `null` to `null` would call work that
 * doesn't exist yet "unchanged" and let a reload discard it silently. */
function designIdentity(inputs: CanvasDesignInputs): string {
  return canonicalize({
    color: inputs.color,
    nominalHeightMm: inputs.nominalHeightMm,
    nominalWidthMm: inputs.nominalWidthMm,
    product: inputs.product,
    systemId: inputs.systemId,
  });
}

/** JSON.stringify with recursively sorted keys — a stable identity for
 * comparing loaded/saved designs against the live inputs. */
function canonicalize(value: unknown): string {
  const order = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(order);
    if (node !== null && typeof node === "object") {
      return Object.fromEntries(
        Object.keys(node as Record<string, unknown>)
          .sort()
          .map((key) => [key, order((node as Record<string, unknown>)[key])]),
      );
    }
    return node;
  };
  return JSON.stringify(order(value));
}

function PositionWorkspace({
  orgId,
  projectId,
  positionId,
  copyId,
  preferredSystem,
}: {
  orgId: string;
  projectId: string;
  positionId: string;
  copyId: string;
  preferredSystem: string | null;
}): JSX.Element {
  const navigate = useNavigate();
  const [loaded, setLoaded] = useState(false);
  const [saved, setSaved] = useState<PositionResponse | null>(null);
  const [result, setResult] = useState<EngineCalculateResponse | null>(null);
  const [location, setLocation] = useState("");
  const [quantity, setQuantity] = useState("1");
  // The breadcrumb leaf is the estimator's own tag («Dormitorio») — the
  // shell falls back to «Vano» while the field is blank.
  useShellLeaf(location.trim() || null);
  // null baseline = nothing persisted yet for this route (copy) → always dirty.
  const [baseline, setBaseline] = useState<{
    design: string;
    location: string;
    quantity: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const mutationLock = useRef(false);
  const [message, setMessage] = useState("");
  const [uncertainCreate, setUncertainCreate] = useState(false);
  const [assemblyEval, setAssemblyEval] = useState<EngineAssemblyCalculateResponse | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  // Bump when a starter replaces the product — the canvas re-fits even if
  // the user had panned/zoomed the previous drawing away.
  const [viewEpoch, setViewEpoch] = useState(0);
  // Unsaved-draft buffer: a reload used to silently discard the design.
  // A pending draft is offered back explicitly — never auto-applied.
  const draftKey = positionDraftKey(orgId, positionId || null, copyId || null);
  const [pendingDraft, setPendingDraft] = useState<PositionDraft | null>(null);
  // New positions open on the design library (the start point); saved ones go
  // straight to the canvas — picking a starter collapses it.
  const [libraryOpen, setLibraryOpen] = useState(!positionId && !copyId);
  const generation = useRef(0);
  const inputs = useCanvasStore((s) => s.inputs);
  const canUndo = useCanvasStore((s) => s.past.length > 0);
  const canRedo = useCanvasStore((s) => s.future.length > 0);
  // The assistant's "this" is the user's current canvas selection — a
  // volatile ref: it reaches the context projection but never keys the
  // durable thread/job (VOLATILE_REFS strips it server-side, and the dock
  // keys threads on stable refs).
  const canvasSelection = useCanvasStore((s) => s.selection);
  useAssistantSurface(
    positionId ? "position" : null,
    positionId
      ? {
          project_id: projectId,
          position_id: positionId,
          ...(canvasSelection ? { selection: canvasSelection } : {}),
        }
      : undefined,
  );
  const systemId = inputs.systemId ?? "";
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const systems = useQuery({
    queryKey: ["project-systems", orgId],
    queryFn: async () => {
      const response = await engineSystems(requestOptions);
      if (response.status !== 200) throw new Error("load");
      return response.data.systems;
    },
    retry: false,
  });
  const options = useQuery({
    queryKey: ["project-design-options", orgId, systemId],
    queryFn: async () => {
      const response = await projectDesignOptions(systemId, requestOptions);
      if (response.status !== 200) throw new Error("load");
      return response.data;
    },
    enabled: !!systemId,
    retry: false,
  });
  // Finishes the series declares. A stored finish it stopped offering still
  // displays — the picker lists it once — but can't save: the engine's color
  // contract is the authority, not this list's length.
  const declaredColors = options.data?.colors ?? [];
  const colorChoices =
    inputs.color && !declaredColors.includes(inputs.color)
      ? [...declaredColors, inputs.color]
      : declaredColors;

  useEffect(() => {
    let active = true;
    const offerDraftIfDivergent = (
      baselineDesign: string,
      baselineLocation: string,
      baselineQuantity: string,
    ) => {
      const draft = readPositionDraft(draftKey);
      if (!draft) return;
      if (
        designIdentity(draft.inputs) !== baselineDesign ||
        draft.location !== baselineLocation ||
        draft.quantity !== baselineQuantity
      )
        setPendingDraft(draft);
      else clearPositionDraft(draftKey);
    };
    if (!positionId && !copyId) {
      const blank = initial();
      // Onboarding hands its picked system over via ?system= so the first
      // position opens on the catalog context the user already chose.
      if (preferredSystem) blank.systemId = preferredSystem;
      useCanvasStore.getState().loadDesign(blank);
      const baselineDesign = designIdentity(blank);
      setBaseline({
        design: baselineDesign,
        location: "",
        quantity: "1",
      });
      offerDraftIfDivergent(baselineDesign, "", "1");
      setLoaded(true);
    } else
      void positionsRetrieve(positionId || copyId, { headers: { "X-Organization-ID": orgId } })
        .then((response) => {
          if (!active) return;
          if (response.status !== 200 || response.data.project_id !== projectId)
            throw new Error("unavailable");
          const item = response.data;

          const tree = item.design.parametric_tree;
          const product: ProductJson = isProductModel(tree)
            ? tree
            : wrapTreeAsProduct(
                tree as IntentNode,
                item.design.nominal_width_mm,
                item.design.nominal_height_mm,
              );
          const loadedInputs = {
            systemId: item.design.system_id,
            nominalWidthMm: item.design.nominal_width_mm,
            nominalHeightMm: item.design.nominal_height_mm,
            // A stored finish the series no longer declares still renders —
            // the picker lists it once so the field is honest, while
            // designPayload refuses to save a finish the engine can't map.
            color: item.design.color,
            parametricTree:
              product.assembly.modules.at(0)?.tree ??
              ({ id: "m1", type: "BAY", opening_type: "FIXED" } as IntentNode),
            product,
          };
          useCanvasStore.getState().loadDesign(loadedInputs);
          setSaved(copyId ? null : item);
          setBaseline(
            copyId
              ? null
              : {
                  design: designIdentity(loadedInputs),
                  location: item.location_tag ?? "",
                  quantity: String(item.quantity),
                },
          );
          offerDraftIfDivergent(
            designIdentity(loadedInputs),
            item.location_tag ?? "",
            String(item.quantity),
          );
          setLocation(item.location_tag ?? "");
          setQuantity(String(item.quantity));
          setResult(item.bom);
          setLoaded(true);
        })
        .catch(() => {
          if (active) setMessage(t("projects.loadError"));
        });
    return () => {
      active = false;
      generation.current += 1;
      useCanvasStore.getState().reset();
    };
  }, [orgId, projectId, positionId, copyId, preferredSystem, draftKey]);

  // Once catalog options arrive, fill uniquely-determined SKUs (coupler when
  // the series has exactly one, mullions for splits created by starters).
  useEffect(() => {
    const product = inputs.product;
    if (!product || !options.data) return;
    const resolved = resolveDefaults(
      product,
      options.data.coupler_skus,
      {
        SPLIT_V: options.data.profiles.find((profile) => profile.role === "MULLION_V")?.sku,
        SPLIT_H: options.data.profiles.find((profile) => profile.role === "MULLION_H")?.sku,
      },
      options.data.glazing_thicknesses.length === 1
        ? options.data.glazing_thicknesses[0]
        : undefined,
      options.data.panel_skus.length === 1 ? options.data.panel_skus[0] : undefined,
    );
    if (resolved !== product) {
      // Deterministic normalization is not a user step: folding it into
      // history would make the preceding change un-undoable.
      useCanvasStore.getState().replaceInputs({ ...inputs, product: resolved });
    }
  }, [inputs, options.data]);

  function applyHistory(direction: "undo" | "redo"): void {
    const store = useCanvasStore.getState();
    if (direction === "undo") store.undo();
    else store.redo();
    setResult(null);
    setAssemblyEval(null);
    setMessage("");
  }

  const onAssemblyChanged = useCallback(() => {
    setResult(null);
    setAssemblyEval(null);
    setMessage("");
  }, []);

  useEffect(() => {
    if (createdId === null) return;
    navigate(`/projects/${projectId}/positions/${createdId}/edit`, { replace: true });
  }, [createdId, navigate, projectId]);

  const onAssemblyEvaluation = useCallback((evaluation: EngineAssemblyCalculateResponse | null) => {
    setAssemblyEval(evaluation);
    setResult(
      evaluation?.bom ? { ...evaluation.bom, calculation_hash: evaluation.calculation_hash } : null,
    );
  }, []);

  // designIdentity deep-serializes the product — memoize on the inputs
  // reference so location/quantity keystrokes skip the canonicalization.
  const identity = useMemo(() => designIdentity(inputs), [inputs]);

  const isDirty =
    baseline === null
      ? true
      : identity !== baseline.design ||
        location !== baseline.location ||
        quantity !== baseline.quantity;

  // Debounced draft write — clears once the design matches the saved state
  // again (including right after a successful save).
  useEffect(() => {
    if (!loaded) return;
    if (!isDirty) {
      clearPositionDraft(draftKey);
      return;
    }
    const timer = setTimeout(
      () => writePositionDraft(draftKey, { inputs, location, quantity, savedAt: Date.now() }),
      600,
    );
    return () => clearTimeout(timer);
  }, [loaded, isDirty, identity, location, quantity, draftKey, inputs]);

  const assemblyUnsaveable =
    assemblyEval?.status === "INVALID" ||
    (assemblyEval?.modules ?? []).some((module) => module.result == null);
  // A disabled Guardar must name the first real blocker ("la hoja queda bajo
  // el ancho mínimo del herraje"), not a generic "revisa los parámetros".
  const saveBlockReason =
    assemblyUnsaveable && assemblyEval !== null && assemblyEval.issues.length > 0
      ? issueText(
          assemblyEval.issues[0]!,
          inputs.product?.assembly.modules ?? [],
          inputs.product?.assembly.couplings ?? [],
        )
      : null;

  async function save(): Promise<void> {
    if (
      uncertainCreate ||
      mutationLock.current ||
      !result ||
      assemblyUnsaveable ||
      busy ||
      !declaredColors.includes(inputs.color) ||
      inputs.product === null ||
      !systemId ||
      !/^[1-9]\d*$/.test(quantity) ||
      Number(quantity) > 2147483647
    )
      return;
    mutationLock.current = true;
    const epoch = ++generation.current;
    setBusy(true);
    setMessage("");
    // A lone unit persists in the classic documentary shape; real assemblies
    // save as product-v2. The in-canvas model is always compositional.
    const design = designPayload(inputs, declaredColors) as PositionDesignRequest;
    const body = {
      location_tag: location,
      quantity: Number(quantity),
      design,
    };
    try {
      const response = saved
        ? await positionsUpdate(
            saved.id,
            { ...body, expected_updated_at: saved.updated_at },
            requestOptions,
          )
        : await positionsCreate(projectId, body, requestOptions);
      if (epoch !== generation.current) return;
      if (response.status !== 200 && response.status !== 201)
        throw new ApiError(response.status, response.data);
      const value = response.data as PositionResponse;
      setSaved(value);
      setResult(value.bom);
      setBaseline({ design: designIdentity(inputs), location, quantity });
      setMessage(t("projects.saved"));
      // The unsaved-changes blocker still sees dirty=true until the baseline
      // commits, so the post-create navigation must wait for the next render.
      if (!positionId) setCreatedId(value.id);
    } catch (error) {
      if (epoch === generation.current) {
        const uncertain = !saved && (!(error instanceof ApiError) || error.status >= 500);
        setUncertainCreate(uncertain);
        setMessage(t(uncertain ? "projects.uncertainPosition" : "projects.saveError"));
      }
    } finally {
      mutationLock.current = false;
      if (epoch === generation.current) setBusy(false);
    }
  }

  if (!loaded) return <p role={message ? "alert" : "status"}>{message || t("projects.loading")}</p>;
  const dirty = isDirty;
  const restoreDraft = (draft: PositionDraft) => {
    const store = useCanvasStore.getState();
    store.loadDesign(draft.inputs);
    setLocation(draft.location);
    setQuantity(draft.quantity);
    setLibraryOpen(false);
    setViewEpoch((epoch) => epoch + 1);
    setPendingDraft(null);
    setMessage("");
  };
  const product = inputs.product;
  const pickStarter = (definition: StarterDefinition) => {
    const { widthMm, heightMm } = starterContextSize(product);
    // The library card previews the starter at its nominal size — building
    // it smaller than that can land a leaf under the hardware minimum (a
    // 1000 mm "Dos hojas" makes two ~440 mm sashes). Floor at nominal so a
    // starter always produces what its thumbnail promised.
    const nominal = starterNominalSize(definition.key);
    const nextProduct = definition.build(
      Math.max(widthMm, nominal.widthMm),
      Math.max(heightMm, nominal.heightMm),
    );
    const store = useCanvasStore.getState();
    store.commitInputs({ ...inputs, product: nextProduct });
    // Coupled starters mint fresh module ids — a stale selection would leave
    // the inspector pointed at a module that no longer exists.
    store.select(nextProduct.assembly.modules[0]?.id ?? null);
    setViewEpoch((epoch) => epoch + 1);
    setLibraryOpen(false);
    onAssemblyChanged();
  };
  // Overview-level position facts — the editable fields live in the
  // .position-head strip; this card answers "what is this vano" at a glance.
  const systemName = systems.data?.find((system) => system.id === inputs.systemId)?.name ?? "—";
  const positionPanel = (
    <section className="assembly-inspector position-panel" aria-label={t("projects.positionData")}>
      <header className="assembly-inspector__header">
        <h4>{t("projects.positionData")}</h4>
      </header>
      <dl className="inspector-summary__list">
        <div className="inspector-summary__row">
          <dt>{t("projects.location")}</dt>
          <dd>{location.trim() || "—"}</dd>
        </div>
        <div className="inspector-summary__row">
          <dt>{t("pricing.quantity")}</dt>
          <dd>{quantity || "1"}</dd>
        </div>
        <div className="inspector-summary__row">
          <dt>{t("projects.system")}</dt>
          <dd>{systemName}</dd>
        </div>
      </dl>
    </section>
  );
  return (
    <section className="projects-page position-editor">
      <UnsavedChangesGuard dirty={dirty} message={t("projects.leaveUnsaved")} />
      <header className="projects-header">
        <div>
          <Link
            className="ui-backlink ui-backlink--back"
            to={projectId ? `/projects/${projectId}` : "/projects"}
          >
            {t("projects.back")}
          </Link>
          <h1>{location || t("projects.position")}</h1>
        </div>
        <span role="status">
          {dirty
            ? t("projects.unsaved")
            : saved === null
              ? t("projects.draft")
              : t("projects.savedState")}
        </span>
        <button disabled={!canUndo || busy} onClick={() => applyHistory("undo")}>
          {t("projects.undo")}
        </button>
        <button disabled={!canRedo || busy} onClick={() => applyHistory("redo")}>
          {t("projects.redo")}
        </button>
        <button
          className="primary-action"
          disabled={uncertainCreate || busy || !result || assemblyUnsaveable}
          title={
            saveBlockReason !== null
              ? `${t("projects.saveBlocked")}: ${saveBlockReason}`
              : !result || assemblyUnsaveable
                ? t("projects.saveBlocked")
                : undefined
          }
          onClick={() => void save()}
        >
          {t("projects.save")}
        </button>
      </header>
      {/* The blocked hint lives BELOW the header row — inside the flex it
       * pushed Deshacer/Guardar left whenever it appeared, and a click aimed
       * at Guardar landed on Deshacer (silent undo). */}
      {loaded && (busy || assemblyUnsaveable || result === null) && (
        <p className="handle-pending" role="status">
          {busy ? t("projects.savingBusy") : (saveBlockReason ?? t("projects.saveBlocked"))}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {pendingDraft !== null && (
        <div className="draft-banner" role="status">
          <span>
            {t("projects.draftFound").replace(
              "{time}",
              new Date(pendingDraft.savedAt).toLocaleString("es-CL", {
                dateStyle: "short",
                timeStyle: "short",
              }),
            )}
          </span>
          <button type="button" onClick={() => restoreDraft(pendingDraft)}>
            {t("projects.restoreDraft")}
          </button>
          <button
            type="button"
            onClick={() => {
              clearPositionDraft(draftKey);
              setPendingDraft(null);
            }}
          >
            {t("projects.discardDraft")}
          </button>
        </div>
      )}
      <fieldset className="position-head" disabled={busy}>
        {/* <fieldset> can't be a flex container — the row wraps the fields
            so the strip stays horizontal. */}
        <div className="position-head__row">
          <label className="position-head__field">
            <span>{t("projects.location")}</span>
            <input
              aria-label={t("projects.location")}
              placeholder={t("projects.locationPlaceholder")}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
          </label>
          <label className="position-head__field">
            <span>{t("pricing.quantity")}</span>
            <input
              inputMode="numeric"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </label>
          <label className="position-head__field position-head__field--wide">
            <span>{t("projects.system")}</span>
            <select
              className="assembly-select"
              aria-label={t("projects.system")}
              value={systemId}
              onChange={(e) => {
                const next = e.target.value || null;
                if (inputs.systemId !== next) {
                  useCanvasStore.getState().commitInputs({ ...inputs, systemId: next });
                  setMessage("");
                }
              }}
            >
              <option value="">{t("projects.chooseSystem")}</option>
              {systems.data
                ?.filter((system) => system.quote_ready)
                .map((system) => (
                  <option key={system.id} value={system.id}>
                    {system.name}
                    {system.is_demo ? ` · ${t("projects.synthetic")}` : ""}
                  </option>
                ))}
            </select>
          </label>
          {(systems.isError || options.isError) && (
            <p className="position-head__alert" role="alert">
              {t("projects.catalogError")}
            </p>
          )}
          {(systems.isPending || (systemId && options.isPending)) && (
            <p className="position-head__alert" role="status">
              {t("projects.loading")}
            </p>
          )}
          <label className="position-head__color">
            <span>{t("projects.color")}</span>
            <select
              className="assembly-select"
              aria-label={t("projects.color")}
              disabled={busy || declaredColors.length === 0}
              value={inputs.color}
              onChange={(event) =>
                useCanvasStore.getState().commitInputs({
                  ...inputs,
                  color: event.target.value as CanvasDesignInputs["color"],
                })
              }
            >
              {colorChoices.length === 0 && <option value={inputs.color}>{inputs.color}</option>}
              {colorChoices.map((color) => (
                <option key={color} value={color}>
                  {tDynamic("projects.color", color)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </fieldset>
      <div className="position-body">
        <div className="position-workspace">
          <details
            className="starter-library"
            open={libraryOpen}
            onToggle={(event) => setLibraryOpen(event.currentTarget.open)}
          >
            <summary>{t("assembly.starterLibrary")}</summary>
            <StarterGallery
              members={resolveMembers(options.data)}
              disabled={busy}
              onPick={pickStarter}
            />
          </details>
          <AssemblyEditor
            organizationId={orgId}
            couplerSkus={options.data?.coupler_skus ?? []}
            glassSkus={options.data?.glass_skus ?? []}
            panelSkus={options.data?.panel_skus ?? []}
            options={options.data}
            optionsReady={options.data !== undefined || options.isError}
            disabled={busy}
            onChanged={onAssemblyChanged}
            onEvaluationChange={onAssemblyEvaluation}
            positionId={saved?.id ?? null}
            positionPanel={positionPanel}
            contentEpoch={viewEpoch}
          />
        </div>
      </div>
      {result ? (
        <ProjectBom result={result} />
      ) : (
        <p role="status">{t("projects.calculationRequired")}</p>
      )}
    </section>
  );
}

export function ProjectBom({ result }: { result: EngineCalculateResponse }): JSX.Element {
  const longestCut = Math.max(0, ...result.profile_cuts.map((cut) => Number(cut.length_mm)));
  return (
    <details className="project-bom">
      <summary>{t("projects.bom")}</summary>
      <div className="projects-table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("pricing.profile")}</th>
              <th>{t("projects.length")}</th>
              <th>{t("pricing.quantity")}</th>
            </tr>
          </thead>
          <tbody>
            {result.profile_cuts.map((cut, index) => (
              <tr key={index}>
                <td>{cut.sku}</td>
                <td>
                  {fmtMm(cut.length_mm)}
                  <CutBar lengthMm={Number(cut.length_mm)} maxMm={longestCut} />
                </td>
                <td>{cut.qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="projects-table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("pricing.glass")}</th>
              <th>{t("projects.pieceWidth")}</th>
              <th>{t("projects.pieceHeight")}</th>
            </tr>
          </thead>
          <tbody>
            {result.glasses.map((glass, index) => (
              <tr key={index}>
                <td>{index + 1}</td>
                <td>{fmtMm(glass.width_mm)}</td>
                <td>{fmtMm(glass.height_mm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.hardware_items.map((kit, index) => (
        <p key={index}>
          {kit.name} × {kit.qty}
        </p>
      ))}
      {(result.fittings ?? []).length > 0 && (
        <div className="projects-table-scroll">
          <table>
            <caption>{t("projects.fittings")}</caption>
            <thead>
              <tr>
                <th>{t("projects.article")}</th>
                <th>{t("assembly.framelessFittings")}</th>
                <th>{t("pricing.quantity")}</th>
              </tr>
            </thead>
            <tbody>
              {(result.fittings ?? []).map((item, index) => (
                <tr key={index}>
                  <td>{item.sku}</td>
                  <td>{tOptional(`assembly.fittingKind.${item.kind}`) ?? item.kind}</td>
                  <td>{item.qty}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result.reinforcements.length > 0 && (
        <div className="projects-table-scroll">
          <table>
            <caption>{t("projects.reinforcements")}</caption>
            <thead>
              <tr>
                <th>{t("pricing.profile")}</th>
                <th>{t("projects.length")}</th>
                <th>{t("pricing.quantity")}</th>
              </tr>
            </thead>
            <tbody>
              {result.reinforcements.map((item, index) => (
                <tr key={index}>
                  <td>{item.reinforcement_sku || item.parent_profile_sku}</td>
                  <td>
                    {fmtMm(item.length_mm)}
                    <CutBar lengthMm={Number(item.length_mm)} maxMm={longestCut} />
                  </td>
                  <td>{item.qty}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result.panels.length > 0 && (
        <div className="projects-table-scroll">
          <table>
            <caption>{t("projects.panels")}</caption>
            <thead>
              <tr>
                <th>{t("projects.article")}</th>
                <th>{t("projects.pieceWidth")}</th>
                <th>{t("projects.pieceHeight")}</th>
              </tr>
            </thead>
            <tbody>
              {result.panels.map((item, index) => (
                <tr key={index}>
                  <td>{item.name}</td>
                  <td>{fmtMm(item.width_mm)}</td>
                  <td>{fmtMm(item.height_mm)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

/** Proportional length bar under a cut dimension — reads the cut plan at a
 * glance the way workshop software shows bar vs remnant. */
function CutBar({ lengthMm, maxMm }: { lengthMm: number; maxMm: number }): JSX.Element | null {
  if (!Number.isFinite(lengthMm) || !Number.isFinite(maxMm) || maxMm <= 0 || lengthMm <= 0)
    return null;
  const pct = Math.min(100, Math.max(2, (lengthMm / maxMm) * 100));
  return (
    <span className="cut-bar" aria-hidden="true">
      <span style={{ width: `${pct}%` }} />
    </span>
  );
}
