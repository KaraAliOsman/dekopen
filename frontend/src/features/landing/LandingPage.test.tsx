import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LandingPage } from "./LandingPage";

describe("LandingPage", () => {
  it("renders hero, the four product sections and a real entry action", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "De la ventana que diseñas al trabajo que entregas" }),
    ).toBeInTheDocument();
    for (const heading of [
      "Diseñar con claridad",
      "Cotizar con producto y precio conectados",
      "Producir con piezas comprensibles",
      "Controlar cambios y entregas",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    const entries = screen.getAllByRole("link", { name: "Entrar" });
    expect(entries.length).toBeGreaterThanOrEqual(2);
    for (const link of entries) expect(link).toHaveAttribute("href", "/login");
    // Every section shows a real product capture, not stock imagery.
    const images = screen
      .getAllByRole("img")
      .filter((node): node is HTMLImageElement => node instanceof HTMLImageElement);
    expect(images.length).toBeGreaterThanOrEqual(5);
    for (const img of images) {
      expect(img.getAttribute("src")).toMatch(/^\/landing\/.+\.webp$/);
    }
  });
});
