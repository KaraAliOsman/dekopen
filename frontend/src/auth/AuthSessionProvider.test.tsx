import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/apiMutator";
import { authMe } from "../api/generated/dekopen";
import { CommercialPricingPage } from "../features/pricing/PricingPage";
import { useCanvasStore } from "../features/canvas/canvasStore";
import { t } from "../i18n/es-CL";
import { telemetry } from "../telemetry/telemetry";
import { AuthSessionProvider, useAuthSession } from "./AuthSessionProvider";

const fake = vi.hoisted(() => ({
  callback: null as ((event: string, session: Session | null) => void) | null,
  getSession: vi.fn(),
  getAssurance: vi.fn(),
  signInWithOtp: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("./supabaseClient", () => ({
  supabase: {
    auth: {
      getSession: fake.getSession,
      onAuthStateChange: (callback: typeof fake.callback) => {
        fake.callback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
      signInWithOtp: fake.signInWithOtp,
      signOut: fake.signOut,
      mfa: { getAuthenticatorAssuranceLevel: fake.getAssurance },
    },
  },
}));
vi.mock("../api/generated/dekopen", () => ({
  authMe: vi.fn(),
  projectsList: vi.fn().mockResolvedValue({ status: 200, data: { items: [] } }),
}));

function sessionFor(userId: string, accessToken: string): Session {
  return {
    access_token: accessToken,
    user: { id: userId },
  } as Session;
}

const session = sessionFor("unit-user", "unit-session-only");

function result(org: string, userId = "unit-user"): Awaited<ReturnType<typeof authMe>> {
  return {
    status: 200,
    headers: new Headers(),
    data: {
      user: { id: userId, email: "" },
      aal: "aal1",
      active_organization: { id: org, name: org, role: "ESTIMATOR" },
      memberships: [],
    },
  };
}

function Probe(): JSX.Element {
  const auth = useAuthSession();
  return (
    <>
      <span data-testid="status">{auth.status}</span>
      <span data-testid="active-org">{auth.me?.active_organization?.id ?? ""}</span>
      <button onClick={() => void auth.selectOrganization("org-B")}>Select B</button>
      <button onClick={() => void auth.requestMagicLink("fixture@example.com")}>Magic link</button>
      <button onClick={() => void auth.signOut()}>Sign out</button>
    </>
  );
}

function DraftSurface(): JSX.Element {
  const auth = useAuthSession();
  return (
    <>
      <span data-testid="status">{auth.status}</span>
      <button onClick={() => void auth.selectOrganization("org-B")}>Select draft B</button>
      {auth.status === "ready" ? (
        <MemoryRouter>
          <CommercialPricingPage />
        </MemoryRouter>
      ) : null}
    </>
  );
}

function mount(child: JSX.Element = <Probe />): void {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthSessionProvider>{child}</AuthSessionProvider>
    </QueryClientProvider>,
  );
}

function seedCanvas(): void {
  act(() => {
    const canvas = useCanvasStore.getState();
    canvas.setSystemId("tenant-a-system");
    canvas.acceptDimension("width", "1444.00");
    canvas.acceptDimension("height", "1555.00");
    canvas.setAnnotations([{ bay_id: "g1", bottom_drain_holes_mm: ["100", "900"] }]);
    canvas.setPreviewDiff({
      diff_id: "tenant-a-diff",
      rule_id: "R07",
      target: { bay_id: "g1", leaf_id: null },
      preconditions: { opening_width_mm: "1444.00", bottom_drain_holes_mm: ["100", "900"] },
      operations: [],
    });
    canvas.setDraftDimension({ axis: "width", value: "1666" });
    canvas.setViewport({ scale: 2, offsetX: 20, offsetY: 30 });
    canvas.toggleSnap();
  });
}

function canvasSnapshot(): object {
  const canvas = useCanvasStore.getState();
  return structuredClone({
    annotations: canvas.annotations,
    previewDiff: canvas.previewDiff,
    inputs: canvas.inputs,
    draftDimension: canvas.draftDimension,
    selection: canvas.selection,
    viewport: canvas.viewport,
    snapEnabled: canvas.snapEnabled,
  });
}

function expectResetCanvas(): void {
  expect(canvasSnapshot()).toEqual({
    annotations: [],
    previewDiff: null,
    inputs: {
      systemId: null,
      nominalWidthMm: "1000.00",
      nominalHeightMm: "1000.00",
      color: "WHITE",
      colorExterior: "",
      parametricTree: {
        id: "g1",
        type: "BAY",
        opening_type: "FIXED",
        glass_thickness_mm: "4.00",
        glass_spec: "4 Float Incoloro",
      },
      product: null,
    },
    draftDimension: null,
    selection: "g1",
    viewport: { scale: 1, offsetX: 0, offsetY: 0 },
    snapEnabled: true,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  fake.callback = null;
  fake.getSession.mockResolvedValue({ data: { session }, error: null });
  fake.getAssurance.mockResolvedValue({ data: { currentLevel: "aal1" }, error: null });
  fake.signInWithOtp.mockResolvedValue({ data: {}, error: null });
  fake.signOut.mockResolvedValue({ error: null });
  useCanvasStore.getState().reset();
  vi.mocked(authMe).mockReset().mockResolvedValue(result("org-A"));
});

describe("authoritative session and active-organization boundary", () => {
  it("resolves a session without copying its access token into a second store", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("active-org")).toHaveTextContent("org-A");
    expect(Object.keys(localStorage)).toEqual(["dekopen.active_org.unit-user"]);
    expect(localStorage.getItem("dekopen.active_org.unit-user")).toBe("org-A");
  });

  it("removes a revoked selection and retries only once to request current memberships", async () => {
    localStorage.setItem("dekopen.active_org.unit-user", "revoked-org");
    vi.mocked(authMe)
      .mockRejectedValueOnce(new ApiError(403, { error: { code: "organization_access_denied" } }))
      .mockRejectedValueOnce(
        new ApiError(409, {
          error: { code: "organization_selection_required" },
          memberships: [],
        }),
      );
    mount();
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("organization_required"),
    );
    expect(authMe).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem("dekopen.active_org.unit-user")).toBeNull();
  });

  it("cannot restore an old authenticated context after SIGNED_OUT", async () => {
    let finish: ((value: Awaited<ReturnType<typeof authMe>>) => void) | undefined;
    vi.mocked(authMe).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount();
    await waitFor(() => expect(authMe).toHaveBeenCalledOnce());
    act(() => fake.callback?.("SIGNED_OUT", null));
    await act(async () => {
      finish?.(result("org-A"));
    });
    expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    expect(screen.getByTestId("active-org")).toBeEmptyDOMElement();
  });

  it("cannot overwrite active B with the delayed response for active A", async () => {
    let finishA: ((value: Awaited<ReturnType<typeof authMe>>) => void) | undefined;
    vi.mocked(authMe)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishA = resolve;
          }),
      )
      .mockResolvedValueOnce(result("org-B"));
    mount();
    await waitFor(() => expect(authMe).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Select B" }));
    await waitFor(() => expect(screen.getByTestId("active-org")).toHaveTextContent("org-B"));
    await act(async () => {
      finishA?.(result("org-A"));
    });
    expect(screen.getByTestId("active-org")).toHaveTextContent("org-B");
    expect(localStorage.getItem("dekopen.active_org.unit-user")).toBe("org-B");
  });

  it("resets canvas before an active-organization replacement can resolve", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    let finishB: ((value: Awaited<ReturnType<typeof authMe>>) => void) | undefined;
    vi.mocked(authMe).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishB = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Select B" }));
    expectResetCanvas();
    await act(async () => finishB?.(result("org-B")));
    await waitFor(() => expect(screen.getByTestId("active-org")).toHaveTextContent("org-B"));
  });

  it("resets canvas after sign-out succeeds", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(fake.signOut).toHaveBeenCalledOnce());
    await waitFor(expectResetCanvas);
  });

  it("preserves canvas when sign-out fails and logical identity does not change", async () => {
    fake.signOut.mockResolvedValueOnce({ error: new Error("controlled sign-out failure") });
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    const before = canvasSnapshot();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
    expect(canvasSnapshot()).toEqual(before);
  });

  it("resets canvas before a different authenticated user can resolve", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    vi.mocked(authMe).mockResolvedValueOnce(result("org-B", "unit-user-B"));
    act(() => fake.callback?.("SIGNED_IN", sessionFor("unit-user-B", "user-b-token")));
    expectResetCanvas();
    await waitFor(() => expect(screen.getByTestId("active-org")).toHaveTextContent("org-B"));
  });

  it("preserves canvas for a same-user same-organization token refresh", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    const before = canvasSnapshot();
    vi.mocked(authMe).mockResolvedValueOnce(result("org-A"));
    act(() => fake.callback?.("TOKEN_REFRESHED", sessionFor("unit-user", "refreshed-token")));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(canvasSnapshot()).toEqual(before);
  });

  it("never leaves ready while a same-user token refresh re-resolves", async () => {
    // The mid-session "resolving" dip unmounted every guarded route and
    // wiped in-flight editor drafts (designer review P0-2).
    const seen: string[] = [];
    function StatusSpy(): null {
      seen.push(useAuthSession().status);
      return null;
    }
    mount(<StatusSpy />);
    await waitFor(() => expect(seen).toContain("ready"));
    seen.length = 0;
    vi.mocked(authMe).mockResolvedValueOnce(result("org-A"));
    act(() => fake.callback?.("TOKEN_REFRESHED", sessionFor("unit-user", "refreshed-token")));
    await waitFor(() => expect(authMe).toHaveBeenCalledTimes(2));
    expect(seen).not.toContain("resolving");
    expect(seen[seen.length - 1]).toBe("ready");
  });

  it("retains the resolved context when a same-user refresh fetch fails", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    vi.mocked(authMe).mockRejectedValueOnce(new Error("network down"));
    await act(async () => {
      fake.callback?.("TOKEN_REFRESHED", sessionFor("unit-user", "refreshed-token"));
      await Promise.resolve();
    });
    await waitFor(() => expect(authMe).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("status")).toHaveTextContent("ready");
    expect(screen.getByTestId("active-org")).toHaveTextContent("org-A");
  });

  it("cannot expose tenant A design through CommercialDraft after selecting tenant B", async () => {
    mount(<DraftSurface />);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    seedCanvas();
    expect(screen.getByText("1444.00 × 1555.00 mm")).toBeInTheDocument();
    let finishB: ((value: Awaited<ReturnType<typeof authMe>>) => void) | undefined;
    vi.mocked(authMe).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishB = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Select draft B" }));
    expectResetCanvas();
    await act(async () => finishB?.(result("org-B")));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByText(t("pricing.prepareDesign"))).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: t("pricing.createDraft") }),
    ).not.toBeInTheDocument();
  });

  it("does not call async Auth methods from inside onAuthStateChange", async () => {
    const capture = vi.spyOn(telemetry, "capture");
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    act(() => {
      fake.callback?.("SIGNED_IN", session);
      expect(fake.getAssurance).not.toHaveBeenCalled();
    });
    await waitFor(() => expect(fake.getAssurance).toHaveBeenCalledOnce());
    expect(capture).toHaveBeenCalledWith("auth_signed_in", { aal: "aal1" });
  });

  it("requests the canonical implicit Magic Link and captures only its approved event", async () => {
    const capture = vi.spyOn(telemetry, "capture");
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Magic link" }));
    await waitFor(() => expect(fake.signInWithOtp).toHaveBeenCalledOnce());
    expect(fake.signInWithOtp).toHaveBeenCalledWith({
      email: "fixture@example.com",
      options: {
        shouldCreateUser: false,
        emailRedirectTo: new URL("/auth/callback", window.location.origin).href,
      },
    });
    expect(capture).toHaveBeenCalledWith("auth_magic_link_requested");
  });
});
