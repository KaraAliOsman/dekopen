/** Validación en español — la fórmula §4: qué pasó + qué hacer, tuteando,
 * sin globos del navegador. Todos los <form> llevan `noValidate`; este
 * módulo se instala una vez (main.tsx) y captura el submit de cualquier
 * formulario: evalúa las restricciones nativas + `data-pattern`, marca el
 * primer campo errado, lo enfoca y lo lleva a la vista.
 *
 * Atributos de control reconocidos:
 * - `data-pattern="regex"` — patrón propio (reemplaza al atributo nativo
 *   `pattern` para que el mensaje nunca sea el inglés del navegador).
 * - `data-error="…"` — mensaje completo para cualquier falla.
 * - `data-error-required="…"` — mensaje cuando falta el dato.
 * - `data-error-pattern="…"` — mensaje cuando el formato no corresponde.
 */

type FieldElement = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

const ERROR_CLASS = "ui-field__error";
const INVALID_ATTR = "data-validation-error";

/** Mensaje §4 para el estado de un campo — primero las pistas declaradas
 * en data-error-*, después el mapa por restricción. */
export function esErrorFor(field: FieldElement): string {
  const v = field.validity;
  const override = field.dataset.error;
  if (v.customError) return field.validationMessage || override || "Revisa este campo.";
  if (v.valueMissing) {
    return field.dataset.errorRequired ?? override ?? "Este campo es obligatorio.";
  }
  if (v.typeMismatch || v.badInput) {
    const type = field.getAttribute("type");
    if (type === "email") {
      return field.dataset.errorPattern ?? override ?? "Ingresa un correo válido.";
    }
    if (type === "number") {
      return field.dataset.errorPattern ?? override ?? "Ingresa un número.";
    }
    return override ?? "El formato no corresponde: revisa el valor.";
  }
  if (v.tooShort) {
    const min = field.getAttribute("minlength");
    return override ?? `Ingresa al menos ${min} caracteres.`;
  }
  if (v.tooLong) {
    const max = field.getAttribute("maxlength");
    return override ?? `Máximo ${max} caracteres.`;
  }
  if (v.rangeUnderflow) {
    const min = field.getAttribute("min");
    return override ?? `El mínimo es ${min}.`;
  }
  if (v.rangeOverflow) {
    const max = field.getAttribute("max");
    return override ?? `El máximo es ${max}.`;
  }
  if (v.stepMismatch) return override ?? "El valor no corresponde al paso permitido.";
  if (v.patternMismatch) {
    return field.dataset.errorPattern ?? override ?? "El formato no corresponde: revisa el valor.";
  }
  return override ?? "Revisa este campo.";
}

/** Comprueba el `data-pattern` declarado — el navegador no lo evalúa. */
function patternError(field: FieldElement): boolean {
  const pattern = field.dataset.pattern;
  if (!pattern || field.value === "") return false;
  try {
    return !new RegExp(`^(?:${pattern})$`).test(field.value);
  } catch {
    return false;
  }
}

function fieldsOf(form: HTMLFormElement): FieldElement[] {
  return Array.from(form.elements).filter(
    (el): el is FieldElement =>
      el instanceof HTMLInputElement ||
      el instanceof HTMLSelectElement ||
      el instanceof HTMLTextAreaElement,
  );
}

function errorKey(field: FieldElement): string {
  return field.name || field.id || "field";
}

/** Marca el campo: aria-invalid + nodo de error justo después (o dentro de
 * su .ui-field). El campo conserva el foco de la corrección. */
function mark(field: FieldElement, message: string): void {
  field.setAttribute("aria-invalid", "true");
  field.setAttribute(INVALID_ATTR, "true");
  const host = field.closest(".ui-field") ?? field.parentElement;
  if (!host) return;
  let node = host.querySelector<HTMLElement>(
    `.${ERROR_CLASS}[data-field-error-for="${errorKey(field)}"]`,
  );
  if (!node) {
    node = document.createElement("p");
    node.className = ERROR_CLASS;
    node.setAttribute("role", "alert");
    node.dataset.fieldErrorFor = errorKey(field);
    host.appendChild(node);
  }
  node.textContent = message;
  const id = `${errorKey(field)}-error`;
  node.id = id;
  field.setAttribute("aria-describedby", id);
}

function unmark(field: FieldElement): void {
  field.removeAttribute("aria-invalid");
  field.removeAttribute(INVALID_ATTR);
  field.removeAttribute("aria-describedby");
  // Solo el nodo del propio campo: los errores de hermanos se quedan.
  const form = field.form;
  form?.querySelector(`.${ERROR_CLASS}[data-field-error-for="${errorKey(field)}"]`)?.remove();
}

/** Valida el formulario: restricciones nativas + data-pattern. Devuelve el
 * primer campo errado o null. Marca todos los errados en español. */
export function validateForm(form: HTMLFormElement): FieldElement | null {
  let first: FieldElement | null = null;
  for (const field of fieldsOf(form)) {
    const nativeBad = !field.checkValidity();
    const patternBad = !nativeBad && patternError(field);
    if (!nativeBad && !patternBad) {
      unmark(field);
      continue;
    }
    const message = patternBad
      ? (field.dataset.errorPattern ??
        field.dataset.error ??
        "El formato no corresponde: revisa el valor.")
      : esErrorFor(field);
    mark(field, message);
    if (!first) first = field;
  }
  return first;
}

/** Instalación global — captura submit e input en todo el documento. Cada
 * formulario con noValidate queda cubierto sin cablear nada por página. */
export function installSpanishValidation(root: Document | HTMLElement = document): () => void {
  const onSubmit = (event: Event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const first = validateForm(form);
    if (first) {
      event.preventDefault();
      event.stopPropagation();
      first.focus();
      // jsdom y navegadores antiguos no exponen scrollIntoView.
      first.scrollIntoView?.({ block: "center", behavior: "smooth" });
    }
  };
  const onInput = (event: Event) => {
    const field = event.target;
    if (
      field instanceof HTMLInputElement ||
      field instanceof HTMLSelectElement ||
      field instanceof HTMLTextAreaElement
    ) {
      if (field.hasAttribute(INVALID_ATTR) && field.checkValidity() && !patternError(field)) {
        unmark(field);
      }
    }
  };
  root.addEventListener("submit", onSubmit, true);
  root.addEventListener("input", onInput, true);
  return () => {
    root.removeEventListener("submit", onSubmit, true);
    root.removeEventListener("input", onInput, true);
  };
}
