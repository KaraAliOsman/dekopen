import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button, Field, NumberField, SelectField, TextInput } from "./Controls";

describe("Button", () => {
  it("blocks a second submit while loading and keeps the label mounted", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Guardar
      </Button>,
    );
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Guardar");
  });

  it("exposes the unavailable reason while disabled", () => {
    render(
      <Button disabled disabledReason="Necesita un proyecto seleccionado">
        Emitir
      </Button>,
    );
    expect(screen.getByRole("button")).toHaveAttribute(
      "title",
      "Necesita un proyecto seleccionado",
    );
  });
});

describe("Field", () => {
  it("renders persistent label, help and an announced error", () => {
    render(
      <Field error="Fuera de rango" help="En milímetros" htmlFor="ancho" label="Ancho">
        <input className="ui-field__input" id="ancho" />
      </Field>,
    );
    const input = screen.getByLabelText("Ancho");
    expect(input).toHaveAttribute("id", "ancho");
    expect(screen.getByRole("alert")).toHaveTextContent("Fuera de rango");
    expect(screen.getByText("En milímetros")).toHaveAttribute("id", "ancho-help");
  });
});

describe("NumberField", () => {
  it("keeps the typed value verbatim and formats only for display when unfocused", () => {
    const onValueChange = vi.fn();
    render(<NumberField decimals={2} onValueChange={onValueChange} value="12500.5" />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("12.500,50");
    fireEvent.focus(input);
    expect(input).toHaveValue("12500.5");
    fireEvent.change(input, { target: { value: "12500.75" } });
    expect(onValueChange).toHaveBeenLastCalledWith("12500.75");
  });

  it("keeps empty and zero distinct", () => {
    render(
      <>
        <NumberField aria-label="vacio" decimals={2} onValueChange={() => {}} value="" />
        <NumberField aria-label="cero" decimals={2} onValueChange={() => {}} value="0" />
      </>,
    );
    expect(screen.getByLabelText("vacio")).toHaveValue("");
    expect(screen.getByLabelText("cero")).toHaveValue("0,00");
  });
});

describe("TextInput", () => {
  it("renders prefix/suffix around the control, not inside the value", () => {
    render(<TextInput prefix="$" readOnly suffix="CLP" value="1000" />);
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("1000");
    expect(input.closest(".ui-input-affix")).toHaveTextContent("$CLP");
  });
});

describe("SelectField", () => {
  it("shows a real message instead of an empty dropdown when nothing is compatible", () => {
    render(<SelectField emptyMessage="Sin opciones compatibles" options={[]} />);
    expect(screen.getByRole("note")).toHaveTextContent("Sin opciones compatibles");
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("keeps a disabled placeholder distinct from a real selection", () => {
    render(
      <SelectField
        options={[{ label: "Blanco", value: "white" }]}
        placeholder="Selecciona acabado"
        value="white"
      />,
    );
    const select = screen.getByRole("combobox");
    const placeholder = select.querySelector("option[disabled]");
    expect(placeholder).toHaveTextContent("Selecciona acabado");
    expect(select).toHaveValue("white");
  });
});
