/** Validación §4 — los mensajes en español, el foco al primer error y el
 * envío bloqueado. El navegador nunca habla: `noValidate` en todos los
 * formularios y este módulo toma el submit. */
import { beforeEach, describe, expect, it } from "vitest";

import { esErrorFor, installSpanishValidation, validateForm } from "./validation";

function mount(html: string): HTMLFormElement {
  document.body.innerHTML = html;
  return document.body.querySelector("form") as HTMLFormElement;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("esErrorFor", () => {
  it("obligatorio → mensaje en español", () => {
    const input = document.createElement("input");
    input.required = true;
    expect(esErrorFor(input)).toBe("Este campo es obligatorio.");
  });
  it("email inválido → pista de correo", () => {
    const input = document.createElement("input");
    input.type = "email";
    input.value = "no-es-correo";
    expect(input.validity.typeMismatch).toBe(true);
    expect(esErrorFor(input)).toBe("Ingresa un correo válido.");
  });
  it("pistas data-error-* tienen precedencia", () => {
    const input = document.createElement("input");
    input.required = true;
    input.dataset.errorRequired = "El cliente necesita un nombre.";
    expect(esErrorFor(input)).toBe("El cliente necesita un nombre.");
  });
});

describe("validateForm", () => {
  it("marca el campo errado y devuelve el primero", () => {
    const form = mount(`
      <form noValidate>
        <div class="ui-field"><input name="nombre" required /></div>
        <input name="ok" />
      </form>`);
    const bad = validateForm(form);
    expect(bad?.name).toBe("nombre");
    expect(form.querySelector(".ui-field__error")?.textContent).toBe("Este campo es obligatorio.");
    expect(form.querySelector("input")?.getAttribute("aria-invalid")).toBe("true");
  });
  it("data-pattern bloquea aunque el campo pase nativo", () => {
    const form = mount(`
      <form noValidate>
        <input name="qty" data-pattern="[0-9]+" value="abc" />
      </form>`);
    const bad = validateForm(form);
    expect(bad?.name).toBe("qty");
    expect(form.querySelector(".ui-field__error")?.textContent).toContain("formato no corresponde");
  });
  it("formulario válido no marca nada", () => {
    const form = mount(`
      <form noValidate>
        <input name="x" required value="dato" />
      </form>`);
    expect(validateForm(form)).toBeNull();
    expect(form.querySelector(".ui-field__error")).toBeNull();
  });
});

describe("installSpanishValidation", () => {
  it("bloquea el submit y enfoca el primer error", () => {
    const form = mount(`
      <form noValidate>
        <div class="ui-field"><input name="cliente" required /></div>
        <button type="submit">Guardar</button>
      </form>`);
    const uninstall = installSpanishValidation(document);
    const input = form.querySelector("input") as HTMLInputElement;
    let focused = false;
    input.focus = () => {
      focused = true;
    };
    input.scrollIntoView = () => {};
    const event = new Event("submit", { bubbles: true, cancelable: true });
    form.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(focused).toBe(true);
    uninstall();
  });
  it("limpia la marca cuando el usuario corrige", () => {
    const form = mount(`
      <form noValidate>
        <div class="ui-field"><input name="cliente" required /></div>
      </form>`);
    const uninstall = installSpanishValidation(document);
    const input = form.querySelector("input") as HTMLInputElement;
    input.focus = () => {};
    input.scrollIntoView = () => {};
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(input.getAttribute("aria-invalid")).toBe("true");
    input.value = "Juan";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(form.querySelector(".ui-field__error")).toBeNull();
    uninstall();
  });
});
