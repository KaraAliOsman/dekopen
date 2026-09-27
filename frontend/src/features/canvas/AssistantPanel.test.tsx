import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { positionsDesignAssist } from "../../api/generated/dekopen";
import { AssistantPanel } from "./AssistantPanel";
import { makeBowProduct, type ProductJson } from "./productEditing";

vi.mock("../../api/generated/dekopen", () => ({ positionsDesignAssist: vi.fn() }));
const assistMock = vi.mocked(positionsDesignAssist);

function bow(): ProductJson {
  return makeBowProduct({ moduleCount: 3, widthMm: 2100, heightMm: 1400, angleDeg: 15 });
}

function renderPanel(overrides: Partial<Parameters<typeof AssistantPanel>[0]> = {}) {
  const props = {
    organizationId: "org-1",
    positionId: "pos-1",
    systemId: "system-a",
    product: bow(),
    disabled: false,
    draft: null,
    onDraftHandled: () => {},
    onApply: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<AssistantPanel {...props} />) };
}

function successResponse() {
  return {
    status: 200,
    headers: new Headers(),
    data: {
      audit_id: "a1",
      model: "mimo",
      credits_debited: 1,
      ops: [{ op: "set_height", height_mm: "1600" }],
      rejected: [],
      notes: null,
    },
  };
}

describe("AssistantPanel system binding", () => {
  beforeEach(() => assistMock.mockReset());

  it("drops the response when the system changes mid-flight", async () => {
    let resolve!: (value: ReturnType<typeof successResponse>) => void;
    assistMock.mockReturnValue(new Promise((r) => (resolve = r)) as never);
    const { props, rerender } = renderPanel();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alto 1600" } });
    fireEvent.click(screen.getByRole("button", { name: /Generar|generar/i }));
    expect(assistMock).toHaveBeenCalledTimes(1);
    // The catalog switches while the request is in flight.
    rerender(<AssistantPanel {...props} systemId="system-b" />);
    resolve(successResponse());
    await waitFor(() => expect(screen.queryByText(/mimo/)).toBeNull());
    expect(screen.queryByRole("button", { name: /Aplicar/i })).toBeNull();
  });

  it("clears a shown preview when the system changes", async () => {
    assistMock.mockResolvedValue(successResponse() as never);
    const { props, rerender } = renderPanel();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "alto 1600" } });
    fireEvent.click(screen.getByRole("button", { name: /Generar|generar/i }));
    const apply = await screen.findByRole("button", { name: /Aplicar/i });
    expect(apply).toBeTruthy();
    rerender(<AssistantPanel {...props} systemId="system-b" />);
    await waitFor(() => expect(screen.queryByRole("button", { name: /Aplicar/i })).toBeNull());
    // The system-A proposal is gone entirely — nothing left to apply under B.
    expect(screen.queryByText(/mimo/)).toBeNull();
  });
});

describe("AssistantPanel queued drafts", () => {
  beforeEach(() => assistMock.mockReset());

  it("submits a fix draft straight away — one click produces a proposal", async () => {
    assistMock.mockResolvedValue(successResponse() as never);
    renderPanel({ draft: { text: "Corrige este problema: hoja fuera del herraje", submit: true } });
    // No Generate click needed — the draft itself drives the request.
    await waitFor(() => expect(assistMock).toHaveBeenCalledTimes(1));
    const args = assistMock.mock.calls[0]![1] as { prompt: string };
    expect(args.prompt).toContain("hoja fuera del herraje");
    // The proposal renders for the human apply gate.
    await screen.findByRole("button", { name: /Aplicar/i });
  });

  it("a non-submit draft only prefills the prompt", async () => {
    renderPanel({ draft: { text: "Modifica el vano" } });
    await waitFor(() =>
      expect(screen.getByRole("textbox")).toHaveProperty("value", "Modifica el vano"),
    );
    expect(assistMock).not.toHaveBeenCalled();
  });
});
