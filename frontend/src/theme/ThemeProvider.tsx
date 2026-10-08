import { createContext, type PropsWithChildren, useContext, useMemo, useState } from "react";

import { telemetry } from "../telemetry/telemetry";

export type Theme = "light" | "dark";
/** §3.7 — densidades: office (por defecto), workshop (taller, objetivos
 * ≥ 44 px y tema oscuro), document (cotizaciones/hojas). */
export type Density = "office" | "workshop" | "document";

type ThemeContextValue = {
  theme: Theme;
  toggleTheme(): void;
  density: Density;
  setDensity(density: Density): void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function initialTheme(): Theme {
  const stored = window.localStorage.getItem("dekopen.theme");
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function initialDensity(): Density {
  const stored = window.localStorage.getItem("dekopen.density");
  return stored === "workshop" || stored === "document" ? stored : "office";
}

export function ThemeProvider({ children }: PropsWithChildren): JSX.Element {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [density, setDensityState] = useState<Density>(initialDensity);
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.density = density;

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      density,
      toggleTheme() {
        const next = theme === "light" ? "dark" : "light";
        window.localStorage.setItem("dekopen.theme", next);
        document.documentElement.dataset.theme = next;
        telemetry.capture("theme_changed", { theme: next });
        setTheme(next);
      },
      setDensity(next: Density) {
        window.localStorage.setItem("dekopen.density", next);
        document.documentElement.dataset.density = next;
        // La densidad workshop nace en oscuro (§3.7); el usuario puede
        // volver a claro después si lo prefiere.
        if (next === "workshop") {
          window.localStorage.setItem("dekopen.theme", "dark");
          document.documentElement.dataset.theme = "dark";
          setTheme("dark");
        }
        setDensityState(next);
      },
    }),
    [theme, density],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
