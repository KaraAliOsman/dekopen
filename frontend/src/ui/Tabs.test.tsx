import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Tabs, type TabItem } from "./Tabs";

const items: TabItem[] = [
  { id: "a", label: "General" },
  { id: "b", label: "Vidrios" },
  { id: "c", label: "Desactivada", disabled: true },
];

function StatefulTabs(): JSX.Element {
  const [value, setValue] = useState("a");
  return <Tabs items={items} label="Secciones" onChange={setValue} value={value} />;
}

function renderTabs() {
  return render(
    <MemoryRouter>
      <StatefulTabs />
    </MemoryRouter>,
  );
}

describe("Tabs", () => {
  it("marks selection with aria-selected and roving tabindex, not color alone", () => {
    renderTabs();
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveAttribute("tabindex", "0");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    expect(tabs[1]).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tab", { name: "Desactivada" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("roves focus and activates with arrow keys, skipping disabled", () => {
    renderTabs();
    const [first, second] = screen.getAllByRole("tab") as [
      HTMLElement,
      HTMLElement,
    ];
    const list = screen.getByRole("tablist");
    first.focus();
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(second).toHaveFocus();
    expect(second).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(first).toHaveFocus();
    expect(first).toHaveAttribute("aria-selected", "true");
  });

  it("route tabs expose aria-selected from the URL", () => {
    render(
      <MemoryRouter initialEntries={["/vidrios"]}>
        <Tabs
          items={[
            { id: "a", label: "General", to: "/general" },
            { id: "b", label: "Vidrios", to: "/vidrios" },
          ]}
          label="Secciones"
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("tab", { name: "Vidrios" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "false");
  });
});
