import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ProductionOrderTrace, ProductionStep } from "../../api/generated/models";
import { OperatorStepCard } from "./OperatorCard";

const step = (code: string): ProductionStep =>
  ({
    id: "step-1",
    sequence: 1,
    code,
    label: code,
    status: "READY",
    work_center_id: null,
    work_center_code: null,
    work_center_name: null,
    started_at: null,
    finished_at: null,
    actor_id: null,
    note: null,
  }) as unknown as ProductionStep;

const traceWith = (ops: unknown[], stationMap?: Record<string, string>) =>
  ({
    operations: { items: ops, station_map: stationMap },
    stock: { reservations: [], remnants: [], unmapped_stock_skus: [] },
    plan: { bars: [], sheets: [] },
  }) as unknown as ProductionOrderTrace;

const sawOp = {
  operation_id: "op-1",
  kind: "SAW_CUT",
  host: "BAR-01",
  detail: { boundary: "B1" },
};
const memberOp = {
  operation_id: "op-2",
  kind: "END_MACHINING",
  host: "MARCO-01",
  detail: { role: "MULLION_V" },
};

describe("OperatorStepCard legacy op routing", () => {
  afterEach(cleanup);

  it("orders without a station_map show saw ops at CUT and member ops only at MACHINING", () => {
    const trace = traceWith([sawOp, memberOp]);
    const { unmount } = render(
      <OperatorStepCard step={step("WELD")} trace={trace} traceBusy={false} />,
    );
    expect(screen.queryByText("Mecanizado de extremo")).toBeNull();
    expect(screen.queryByText("B1")).toBeNull();
    unmount();

    render(<OperatorStepCard step={step("MACHINING")} trace={trace} traceBusy={false} />);
    expect(screen.getByText("Mecanizado de extremo")).toBeTruthy();
    cleanup();

    render(<OperatorStepCard step={step("CUT")} trace={trace} traceBusy={false} />);
    expect(screen.getByText("B1")).toBeTruthy();
    expect(screen.queryByText("Mecanizado de extremo")).toBeNull();
  });

  it("a declared station_map routes ops to their mapped station", () => {
    const trace = traceWith([sawOp, memberOp], {
      SAW_CUT: "CUT",
      END_MACHINING: "MACHINING",
      HANDLE_PREP: "HARDWARE",
    });
    render(<OperatorStepCard step={step("HARDWARE")} trace={trace} traceBusy={false} />);
    expect(screen.queryByText("Mecanizado de extremo")).toBeNull();
  });
});
