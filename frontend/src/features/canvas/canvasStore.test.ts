import { beforeEach, describe, expect, it } from "vitest";

import { useCanvasStore, type CanvasDesignInputs } from "./canvasStore";
import { makeBowProduct } from "./productEditing";

const BARE = { id: "b1", type: "BAY", opening_type: "FIXED" } as const;

function inputs(patch?: Partial<CanvasDesignInputs>): CanvasDesignInputs {
  return {
    systemId: "s",
    nominalWidthMm: "1000.00",
    nominalHeightMm: "1000.00",
    color: "WHITE",
    colorExterior: "",
    parametricTree: { ...BARE },
    product: null,
    ...patch,
  };
}

beforeEach(() => {
  useCanvasStore.getState().reset();
  useCanvasStore.getState().loadDesign(inputs());
});

describe("design command history", () => {
  it("commitInputs records undoable steps and redo replays them", () => {
    const store = useCanvasStore.getState();
    const v1 = inputs({ nominalWidthMm: "1200.00" });
    const v2 = inputs({ nominalWidthMm: "1300.00" });
    store.commitInputs(v1);
    store.commitInputs(v2);
    expect(useCanvasStore.getState().inputs).toBe(v2);
    expect(useCanvasStore.getState().past).toHaveLength(2);

    useCanvasStore.getState().undo();
    expect(useCanvasStore.getState().inputs).toBe(v1);
    useCanvasStore.getState().undo();
    expect(useCanvasStore.getState().inputs.nominalWidthMm).toBe("1000.00");
    expect(useCanvasStore.getState().past).toHaveLength(0);

    useCanvasStore.getState().redo();
    expect(useCanvasStore.getState().inputs).toBe(v1);
    useCanvasStore.getState().redo();
    expect(useCanvasStore.getState().inputs).toBe(v2);
  });

  it("a new commit clears the redo stack", () => {
    const store = useCanvasStore.getState();
    store.commitInputs(inputs({ nominalWidthMm: "1200.00" }));
    useCanvasStore.getState().undo();
    store.commitInputs(inputs({ nominalWidthMm: "1500.00" }));
    expect(useCanvasStore.getState().future).toHaveLength(0);
    useCanvasStore.getState().redo();
    expect(useCanvasStore.getState().inputs.nominalWidthMm).toBe("1500.00");
  });

  it("undo at the oldest state is a no-op", () => {
    const before = useCanvasStore.getState().inputs;
    useCanvasStore.getState().undo();
    expect(useCanvasStore.getState().inputs).toBe(before);
  });

  it("replaceInputs normalizes without an undo step", () => {
    const store = useCanvasStore.getState();
    const before = useCanvasStore.getState().inputs;
    const v1 = inputs({ nominalWidthMm: "1200.00" });
    const normalized = inputs({ nominalWidthMm: "1250.00" });
    store.commitInputs(v1);
    useCanvasStore.getState().replaceInputs(normalized);
    expect(useCanvasStore.getState().inputs).toBe(normalized);
    expect(useCanvasStore.getState().past).toHaveLength(1);

    useCanvasStore.getState().undo();
    expect(useCanvasStore.getState().inputs).toBe(before);
  });

  it("loadDesign and reset clear history", () => {
    useCanvasStore.getState().commitInputs(inputs({ nominalWidthMm: "9.00" }));
    useCanvasStore.getState().loadDesign(inputs());
    expect(useCanvasStore.getState().past).toHaveLength(0);
    expect(useCanvasStore.getState().future).toHaveLength(0);
  });

  it("selectBay accepts module ids when a product is active", () => {
    const product = makeBowProduct({
      moduleCount: 3,
      widthMm: 2100,
      heightMm: 1400,
      angleDeg: 15,
    });
    useCanvasStore.getState().loadDesign(inputs({ product }));
    expect(useCanvasStore.getState().selection).toBe("m1");
    useCanvasStore.getState().selectBay("m3");
    expect(useCanvasStore.getState().selection).toBe("m3");
    useCanvasStore.getState().selectBay("ghost");
    expect(useCanvasStore.getState().selection).toBe("m3");
  });
});
