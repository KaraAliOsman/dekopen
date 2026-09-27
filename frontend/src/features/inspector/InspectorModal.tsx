import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/apiMutator";
import { engineCalculate, engineInspect, engineOptimizeCut } from "../../api/generated/dekopen";
import type { AnnotationRequest, InspectorDiff } from "../../api/generated/models";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { type CanvasDesignInputs, useCanvasStore } from "../canvas/canvasStore";
import { calculationKey, requestFromInputs } from "../canvas/useEngineCalculation";
import { previewDrainDraft, workshopReadiness } from "./inspectorDraft";
import "./inspector.css";

function humanError(error: unknown): string {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null) {
    const detail = (error.payload as { error?: { detail?: unknown } }).error?.detail;
    if (typeof detail === "string" && !/traceback|exception|select\s|sqlstate/i.test(detail))
      return detail;
  }
  return t("inspector.error");
}

export function InspectorModal({
  open,
  onClose,
  organizationId,
  inputs,
  calculationHash,
}: {
  open: boolean;
  onClose(): void;
  organizationId: string;
  inputs: CanvasDesignInputs;
  calculationHash: string;
}): JSX.Element {
  const dialog = useRef<HTMLDialogElement>(null);
  const cache = useQueryClient();
  const annotations = useCanvasStore((s) => s.annotations);
  const preview = useCanvasStore((s) => s.previewDiff);
  const setAnnotations = useCanvasStore((s) => s.setAnnotations);
  const setPreview = useCanvasStore((s) => s.setPreviewDiff);
  const [tab, setTab] = useState<"inspection" | "cutting">("inspection");
  const [holes, setHoles] = useState("");
  const [continuous, setContinuous] = useState("");
  const [coupler, setCoupler] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(0);
  const [approved, setApproved] = useState(false);
  const currentOrg = useRef(organizationId);
  const mountEpoch = useRef(0);
  useEffect(
    () => () => {
      mountEpoch.current += 1;
    },
    [],
  );
  useEffect(() => {
    currentOrg.current = organizationId;
  }, [organizationId]);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current?.close();
  }, [open]);
  useEffect(() => {
    const item = annotations.find((a) => a.bay_id === inputs.parametricTree.id && !a.leaf_id);
    setHoles(item?.bottom_drain_holes_mm?.join(", ") ?? "");
    setContinuous(item?.continuous_width_mm ?? "");
    setCoupler(
      item?.has_coupler === undefined || item.has_coupler === null
        ? ""
        : item.has_coupler
          ? "yes"
          : "no",
    );
  }, [annotations, inputs.parametricTree.id]);
  const technical = requestFromInputs(inputs);
  const inspectionKey = (draft: AnnotationRequest[]): readonly unknown[] => [
    "engine-inspection",
    organizationId,
    technical,
    draft,
  ];
  const inspection = useQuery({
    queryKey: inspectionKey(annotations),
    enabled: open,
    retry: false,
    queryFn: async () => {
      const response = await engineInspect({ ...technical, annotations, mode: "DESIGN" });
      if (response.status !== 200) throw new Error("unexpected_response");
      return response.data;
    },
  });
  const cutting = useQuery({
    queryKey: ["engine-cutting", organizationId, technical],
    enabled: open,
    retry: false,
    queryFn: async () => {
      const response = await engineOptimizeCut(technical);
      if (response.status !== 200) throw new Error("unexpected_response");
      return response.data;
    },
  });
  const current =
    !busy &&
    !error &&
    !inspection.isFetching &&
    !cutting.isFetching &&
    !inspection.isError &&
    !cutting.isError &&
    inspection.data?.source_calculation_hash === calculationHash &&
    cutting.data?.source_calculation_hash === calculationHash;
  const ready = workshopReadiness(inspection.data?.production_allowed, cutting.isSuccess, current);
  async function apply(diff: InspectorDiff): Promise<void> {
    setBusy(true);
    setError(null);
    setApproved(false);
    const inputIdentity = JSON.stringify(inputs);
    const annotationIdentity = JSON.stringify(annotations);
    const epoch = mountEpoch.current;
    const unchanged = (): boolean =>
      epoch === mountEpoch.current &&
      JSON.stringify(useCanvasStore.getState().inputs) === inputIdentity &&
      JSON.stringify(useCanvasStore.getState().annotations) === annotationIdentity &&
      currentOrg.current === organizationId;
    try {
      const draft = previewDrainDraft(annotations, diff, inputs.nominalWidthMm);
      if (!unchanged()) throw new Error("stale_correction");
      const recalculated = await engineCalculate(technical);
      if (recalculated.status !== 200) throw new Error("calculation_failed");
      if (!unchanged()) throw new Error("stale_correction");
      const checked = await engineInspect({ ...technical, annotations: draft, mode: "DESIGN" });
      if (
        checked.status !== 200 ||
        checked.data.source_calculation_hash !== recalculated.data.calculation_hash ||
        recalculated.data.calculation_hash !== calculationHash ||
        !unchanged()
      ) {
        throw new Error("stale_correction");
      }
      cache.setQueryData(calculationKey(organizationId, inputs), recalculated.data);
      cache.setQueryData(inspectionKey(draft), checked.data);
      setAnnotations(draft);
      setPulse((value) => value + 1);
    } catch (failure) {
      if (epoch === mountEpoch.current) setError(humanError(failure));
    } finally {
      if (epoch === mountEpoch.current) setBusy(false);
    }
  }
  function saveObservations(): void {
    const positions = holes.trim() ? holes.split(",").map((value) => value.trim()) : [];
    if (
      positions.some((p) => !/^\d+(?:\.\d{1,4})?$/.test(p)) ||
      (continuous.trim() !== "" && !/^\d+(?:\.\d{1,4})?$/.test(continuous.trim()))
    ) {
      setError(t("inspector.coordinatesError"));
      return;
    }
    setAnnotations([
      {
        bay_id: inputs.parametricTree.id,
        leaf_id: null,
        bottom_drain_holes_mm: positions,
        continuous_width_mm: continuous.trim() || null,
        // Machining finish class follows the design's declared finish —
        // the workshop annotation domain is WHITE|FOILED (non-white ⇒ foil).
        finish_class: inputs.color === "WHITE" ? "WHITE" : "FOILED",
        has_coupler: coupler === "" ? null : coupler === "yes",
      },
    ]);
    setError(null);
    setApproved(false);
  }
  return (
    <dialog
      ref={dialog}
      className="inspector-modal"
      aria-labelledby="inspector-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
      onClose={onClose}
    >
      <header>
        <h2 id="inspector-title">{t("inspector.title")}</h2>
        <button type="button" onClick={onClose} disabled={busy}>
          {t("inspector.close")}
        </button>
      </header>
      <nav aria-label={t("inspector.sections")}>
        <button
          type="button"
          aria-pressed={tab === "inspection"}
          onClick={() => setTab("inspection")}
        >
          {t("inspector.inspection")}
        </button>
        <button type="button" aria-pressed={tab === "cutting"} onClick={() => setTab("cutting")}>
          {t("inspector.cutting")}
        </button>
      </nav>
      {(error || inspection.isError || cutting.isError) && (
        <p role="alert">{error ?? humanError(inspection.error ?? cutting.error)}</p>
      )}
      {(inspection.isFetching || cutting.isFetching || busy) && (
        <p role="status">{t("inspector.verifying")}</p>
      )}
      <p
        className="inspector-semaphore"
        data-status={inspection.data?.status ?? "PENDING"}
        role="status"
      >
        {inspection.data?.status === "GREEN"
          ? t("inspector.green")
          : inspection.data?.status === "YELLOW"
            ? t("inspector.yellow")
            : inspection.data?.status === "RED"
              ? t("inspector.red")
              : t("inspector.verifying")}
      </p>
      {tab === "inspection" ? (
        <section>
          <fieldset disabled={busy}>
            <legend>{t("inspector.annotations")}</legend>
            <label>
              {t("inspector.drains")}
              <input
                value={holes}
                onChange={(e) => setHoles(e.target.value)}
                placeholder="100, 900"
              />
            </label>
            <label>
              {t("inspector.continuousWidth")}
              <input
                value={continuous}
                onChange={(e) => setContinuous(e.target.value)}
                inputMode="decimal"
              />
            </label>
            <label>
              {t("inspector.coupler")}
              <select value={coupler} onChange={(e) => setCoupler(e.target.value)}>
                <option value="">{t("inspector.unconfirmed")}</option>
                <option value="no">{t("inspector.no")}</option>
                <option value="yes">{t("inspector.yes")}</option>
              </select>
            </label>
            <button type="button" onClick={saveObservations}>
              {t("inspector.verifyAnnotations")}
            </button>
          </fieldset>
          <div
            key={pulse}
            className={pulse > 0 ? "inspector-findings is-corrected" : "inspector-findings"}
          >
            {inspection.data?.findings.map((finding, index) => (
              <article
                key={`${finding.rule_id}-${finding.bay_id}-${finding.leaf_id}-${index}`}
                data-rule={finding.rule_id}
              >
                <h3>{finding.title}</h3>
                <p>{finding.diagnosis}</p>
                <p>{finding.risk}</p>
                <p>{finding.recommendation}</p>
                <p>
                  {finding.fixability === "AUTO_FIXABLE"
                    ? t("inspector.automatic")
                    : finding.fixability === "SUGGESTION_ONLY"
                      ? t("inspector.suggestion")
                      : t("inspector.authorityRequired")}
                </p>
                {finding.fixability === "AUTO_FIXABLE" && finding.fix && (
                  <button
                    type="button"
                    disabled={busy || inspection.isFetching}
                    onClick={() => setPreview(finding.fix)}
                  >
                    {t("inspector.preview")}
                  </button>
                )}
              </article>
            ))}
          </div>
          {preview && (
            <aside className="inspector-diff" aria-label={t("inspector.preview")}>
              <p>
                {t("inspector.before")}: {preview.operations[0]?.old_value.join(", ")} mm
              </p>
              <p>
                {t("inspector.after")}: {preview.operations[0]?.new_value.join(", ")} mm
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  void apply(preview);
                }}
              >
                {t("inspector.apply")}
              </button>
              <button type="button" disabled={busy} onClick={() => setPreview(null)}>
                {t("inspector.cancel")}
              </button>
            </aside>
          )}
        </section>
      ) : (
        <section className="inspector-cutting">
          <h3>{t("inspector.purchase")}</h3>
          <ul>
            {cutting.data?.purchase_list.map((line, i) => (
              <li key={i}>
                <strong>{line.commercial_sku}</strong> · {line.qty_bars} {t("inspector.bars")} ·{" "}
                {fmtMm(line.stock_length_mm)} mm · {line.material} · {line.color}
              </li>
            ))}
          </ul>
          <h3>{t("inspector.workshopPlan")}</h3>
          {cutting.data?.workshop_cut_plan.map((bar) => (
            <article key={bar.bar_index}>
              <h4>
                {t("inspector.bar")} {bar.bar_index} · {fmtMm(bar.stock_length_mm)} mm
              </h4>
              <p>
                {t("inspector.kerf")}: {fmtMm(bar.kerf_total_mm)} mm · {t("inspector.trims")}:{" "}
                {fmtMm(bar.head_trim_mm)} / {fmtMm(bar.tail_trim_mm)} mm ·{" "}
                {t("inspector.remainder")}: {fmtMm(bar.remainder_mm)} mm
              </p>
              <ol>
                {bar.cuts.map((cut) => (
                  <li key={cut.sequence}>
                    <strong>{cut.workshop_sku}</strong> · {fmtMm(cut.length_mm)} mm
                  </li>
                ))}
              </ol>
            </article>
          ))}
        </section>
      )}
      <footer>
        <button type="button" disabled={!ready} onClick={() => setApproved(true)}>
          {t("inspector.approve")}
        </button>
        {approved && ready && <p role="status">{t("inspector.reviewComplete")}</p>}
      </footer>
    </dialog>
  );
}
