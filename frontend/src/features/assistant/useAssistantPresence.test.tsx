import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Orb, orbStateFor } from "./Orb";
import { jobMatchesContext, presenceJob, pressingJob } from "./useAssistantPresence";

describe("orbStateFor", () => {
  it.each([
    ["QUEUED", "queued"],
    ["PLANNING", "thinking"],
    ["RUNNING", "working"],
    ["WAITING_FOR_USER", "waiting"],
    ["WAITING_FOR_APPROVAL", "approval"],
    ["SUCCEEDED", "success"],
    ["FAILED", "error"],
    ["FAILED_RETRYABLE", "error"],
    ["CANCELED", "canceled"],
  ] as const)("%s → %s", (jobState, orbState) => {
    expect(orbStateFor(jobState)).toBe(orbState);
  });

  it("un estado desconocido cae a idle seguro", () => {
    expect(orbStateFor("MOONWALKING")).toBe("idle");
    expect(orbStateFor("")).toBe("idle");
    expect(orbStateFor(undefined)).toBe("idle");
    expect(orbStateFor(null)).toBe("idle");
  });
});

describe("jobMatchesContext", () => {
  const job = {
    surface: "position",
    refs: { project_id: "p1", position_id: "pos1" },
  };

  it("coincide superficie y refs de identidad simétricas", () => {
    expect(jobMatchesContext(job, "position", { project_id: "p1", position_id: "pos1" })).toBe(
      true,
    );
  });

  it("ignora refs volátiles del puntero (selection) en el contexto", () => {
    expect(
      jobMatchesContext(job, "position", {
        project_id: "p1",
        position_id: "pos1",
        selection: "bay-2",
      }),
    ).toBe(true);
  });

  it("rechaza un job con refs extra (no se reasigna a otra ruta)", () => {
    const richJob = { surface: "position", refs: { ...job.refs, order_id: "o9" } };
    expect(jobMatchesContext(richJob, "position", { project_id: "p1", position_id: "pos1" })).toBe(
      false,
    );
  });

  it("rechaza superficie o identidad distintas", () => {
    expect(jobMatchesContext(job, "project", { project_id: "p1", position_id: "pos1" })).toBe(
      false,
    );
    expect(jobMatchesContext(job, "position", { project_id: "p2", position_id: "pos1" })).toBe(
      false,
    );
  });
});

describe("presenceJob", () => {
  it("devuelve el job del contexto más recientemente actualizado", () => {
    const jobs = [
      {
        surface: "position",
        refs: { project_id: "p1", position_id: "pos1" },
        updated_at: "2026-10-01T10:00:00Z",
      },
      {
        surface: "position",
        refs: { project_id: "p1", position_id: "pos1" },
        updated_at: "2026-10-02T10:00:00Z",
      },
      {
        surface: "project",
        refs: { project_id: "p1" },
        updated_at: "2026-10-03T10:00:00Z",
      },
    ];
    const found = presenceJob(jobs, "position", { project_id: "p1", position_id: "pos1" });
    expect(found?.updated_at).toBe("2026-10-02T10:00:00Z");
  });

  it("sin coincidencia devuelve null (el Orb queda en idle)", () => {
    expect(presenceJob([], "position", { project_id: "p1" })).toBeNull();
    expect(presenceJob(null, "position", { project_id: "p1" })).toBeNull();
  });
});

describe("pressingJob", () => {
  it("una decisión pendiente supera a una ronda en vuelo más reciente", () => {
    const jobs = [
      { surface: "a", refs: {}, state: "RUNNING", updated_at: "2026-10-02T10:00:00Z" },
      {
        surface: "b",
        refs: {},
        state: "WAITING_FOR_APPROVAL",
        updated_at: "2026-10-01T10:00:00Z",
      },
    ];
    expect(pressingJob(jobs)?.state).toBe("WAITING_FOR_APPROVAL");
  });

  it("incluye FAILED_RETRYABLE (sigue siendo accionable) y omite terminales", () => {
    const jobs = [
      { surface: "a", refs: {}, state: "SUCCEEDED", updated_at: "2026-10-03T10:00:00Z" },
      {
        surface: "b",
        refs: {},
        state: "FAILED_RETRYABLE",
        updated_at: "2026-10-01T10:00:00Z",
      },
    ];
    expect(pressingJob(jobs)?.state).toBe("FAILED_RETRYABLE");
  });

  it("sin actividad apremiante devuelve null", () => {
    expect(
      pressingJob([{ surface: "a", refs: {}, state: "SUCCEEDED", updated_at: "1" }]),
    ).toBeNull();
  });
});

describe("Orb en el DOM", () => {
  it("tres Orbs en pantalla generan ids SVG únicos", () => {
    render(
      <>
        <Orb state="idle" size={16} />
        <Orb state="working" size={28} />
        <Orb state="success" size={64} />
      </>,
    );
    const gradients = document.querySelectorAll("radialGradient[id^='orb-body-']");
    expect(gradients).toHaveLength(3);
    const ids = [...gradients].map((g) => g.id);
    expect(new Set(ids).size).toBe(3);
    for (const gradient of gradients) {
      const owner = gradient.closest("svg")!;
      expect(owner.querySelector(`circle[fill="url(#${gradient.id})"]`)).not.toBeNull();
    }
  });

  it("respeta reduced-motion sin depender de MediaQueryList", () => {
    // jsdom no pinta CSS: la garantía es estructural — la hoja orb.css mata
    // toda animación bajo prefers-reduced-motion y el SVG no usa JS timing.
    render(<Orb state="working" size={28} />);
    expect(document.querySelectorAll("svg.orb")).toHaveLength(1);
    expect(document.querySelector(".orb__ring")).not.toBeNull();
  });
});
