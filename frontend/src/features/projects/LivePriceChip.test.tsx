import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { t } from "../../i18n/es-CL";
import { LivePriceChip } from "./LivePriceChip";

afterEach(cleanup);

const basePrice = {
  unitNet: "160.0000",
  lineNet: "160.0000",
  netless: false,
  modules: null,
};

it("renderiza el desglose por módulo M1..Mn en orden de alzado", () => {
  const { getByTestId } = render(
    <LivePriceChip
      price={{
        ...basePrice,
        modules: [
          { module_id: "m2", unit_net: "60.0000" },
          { module_id: "m1", unit_net: "80.0000" },
          { module_id: "m3", unit_net: "20.0000" },
        ],
      }}
      pending={false}
      currency="CLP"
      moduleIds={["m1", "m2", "m3"]}
    />,
  );
  // El orden lo marca el alzado (moduleIds), no el orden del payload.
  const split = getByTestId("live-price-modules");
  expect(split.textContent).toContain("M1");
  expect(split.textContent).toContain("M2");
  expect(split.textContent).toContain("M3");
  expect(split.textContent!.indexOf("M1")).toBeLessThan(split.textContent!.indexOf("M2"));
  expect(split.textContent!.indexOf("M2")).toBeLessThan(split.textContent!.indexOf("M3"));
  expect(split.getAttribute("title")).toBe(t("assembly.pricePerModule"));
});

it("sin módulos no dibuja desglose; netless muestra el guion honesto", () => {
  const { getByTestId, queryByTestId, rerender } = render(
    <LivePriceChip price={basePrice} pending={false} currency="CLP" />,
  );
  expect(queryByTestId("live-price-modules")).toBeNull();
  expect(getByTestId("live-price").textContent).toContain(t("projects.netUnit"));

  rerender(
    <LivePriceChip
      price={{ unitNet: "", lineNet: "", netless: true, modules: null }}
      pending={false}
      currency="CLP"
    />,
  );
  // Modo sin neto honesto (lista/matríz): «—» con la razón en el título,
  // nunca un número inventado.
  const chip = getByTestId("live-price");
  expect(chip.textContent).toBe("—");
  expect(chip.querySelector("span")!.getAttribute("title")).toBe(t("projects.netlessHint"));
});
