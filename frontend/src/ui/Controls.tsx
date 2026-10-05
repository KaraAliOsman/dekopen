import {
  Children,
  createContext,
  forwardRef,
  isValidElement,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { moneyDigits } from "../format";
import { t } from "../i18n/es-CL";

/* ---------- Button ---------- */

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "default" | "compact" | "touch";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Busy state: shows a spinner, disables re-submission, keeps width stable. */
  loading?: boolean;
  /** Optional leading icon (svg/span). Decorative — keep labels textual. */
  icon?: ReactNode;
  /** Why the action is unavailable; rendered as title so a disabled control
   * still explains the missing condition. */
  disabledReason?: string;
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "ui-button--primary",
  secondary: "",
  danger: "ui-button--danger",
  ghost: "ui-button--ghost",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "default",
    loading = false,
    icon,
    disabledReason,
    className,
    children,
    disabled,
    type = "button",
    ...rest
  },
  ref,
): JSX.Element {
  const classes = [
    "ui-button",
    VARIANT_CLASS[variant],
    size === "compact" ? "ui-button--compact" : null,
    size === "touch" ? "ui-button--touch" : null,
    loading ? "is-loading" : null,
    className ?? null,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      aria-busy={loading || undefined}
      className={classes}
      disabled={disabled || loading}
      ref={ref}
      title={disabled ? disabledReason : rest.title}
      type={type}
      {...rest}
    >
      {loading ? <span aria-hidden className="ui-button__spinner" /> : null}
      {!loading && icon ? <span className="ui-button__icon">{icon}</span> : null}
      {/* The label stays mounted while loading so width doesn't collapse. */}
      <span className="ui-button__label">{children}</span>
    </button>
  );
});

/* ---------- Field ---------- */

/** Lo que un <Field> entrega al control que envuelve: el id que la
 * etiqueta referencia, los ids de ayuda/error para aria-describedby y la
 * marca inválida. Las primitivas de entrada lo consumen solas — ningún
 * control dentro de un Field queda sin etiqueta accesible. */
type FieldWiring = { id: string; describedBy?: string; invalid: boolean };
const FieldContext = createContext<FieldWiring | null>(null);

function useFieldWiring(invalid?: boolean): {
  id?: string;
  describedBy?: string;
  invalid: boolean;
} {
  const field = useContext(FieldContext);
  return {
    id: field?.id,
    describedBy: field?.describedBy,
    invalid: invalid ?? field?.invalid ?? false,
  };
}

export type FieldProps = {
  /** Persistent label — never swapped for a placeholder. */
  label: string;
  htmlFor?: string;
  help?: string;
  /** Associated error; announced via aria-describedby + role=alert. */
  error?: string | null;
  required?: boolean;
  children: ReactNode;
};

export function Field({
  label,
  htmlFor,
  help,
  error,
  required,
  children,
}: FieldProps): JSX.Element {
  const autoId = useId();
  const fieldId = htmlFor ?? autoId;
  const helpId = `${fieldId}-help`;
  const errorId = `${fieldId}-error`;
  const describedBy =
    [help ? helpId : "", error ? errorId : ""].filter(Boolean).join(" ") || undefined;
  const wiring = useMemo<FieldWiring>(
    () => ({ describedBy, id: fieldId, invalid: Boolean(error) }),
    [describedBy, error, fieldId],
  );
  return (
    <div className={`ui-field${error ? " ui-field--invalid" : ""}`}>
      <label className="ui-field__label" htmlFor={fieldId}>
        {label}
        {required ? (
          <span aria-hidden className="ui-field__required">
            {" "}
            *
          </span>
        ) : null}
      </label>
      {/* El control toma id/aria-describedby/aria-invalid del contexto. */}
      <FieldContext.Provider value={wiring}>{children}</FieldContext.Provider>
      {help ? (
        <p className="ui-field__help" id={helpId}>
          {help}
        </p>
      ) : null}
      {error ? (
        <p className="ui-field__error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/* ---------- inputs ---------- */

export type TextInputProps = InputHTMLAttributes<HTMLInputElement> & {
  /** Trailing unit/prefix shown inside the control box (mm, %, $, UF…). */
  suffix?: string;
  prefix?: string;
  invalid?: boolean;
};

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { suffix, prefix, invalid, className, id, "aria-describedby": describedBy, ...rest },
  ref,
): JSX.Element {
  const field = useFieldWiring(invalid);
  const described = [describedBy, field.describedBy].filter(Boolean).join(" ") || undefined;
  const ariaProps = {
    "aria-describedby": described,
    "aria-invalid": field.invalid || undefined,
    id: id ?? field.id,
  };
  if (suffix || prefix) {
    return (
      <span className={`ui-input-affix${field.invalid ? " is-invalid" : ""}`}>
        {prefix ? <span className="ui-input-affix__part">{prefix}</span> : null}
        <input
          {...ariaProps}
          className={`ui-field__input ui-field__input--bare ${className ?? ""}`}
          ref={ref}
          {...rest}
        />
        {suffix ? <span className="ui-input-affix__part">{suffix}</span> : null}
      </span>
    );
  }
  return (
    <input {...ariaProps} className={`ui-field__input ${className ?? ""}`} ref={ref} {...rest} />
  );
});

/**
 * Numeric/money/dimension input: keeps the caller's string value verbatim,
 * applies optional presentation formatting only on blur, and treats empty,
 * zero and "unknown" as distinct states (empty stays empty; zero is a real
 * number; unknown is null rendered as —).
 */
export type NumberFieldProps = Omit<TextInputProps, "value" | "onChange" | "type"> & {
  value: string;
  onValueChange: (value: string) => void;
  /** Decimal places applied on blur (e.g. 0 for CLP, 1–2 for mm). The stored
   * value is untouched while typing. */
  decimals?: number;
  /** Rendered when the value is empty and the field is not focused. */
  emptyPlaceholder?: string;
};

export function NumberField({
  value,
  onValueChange,
  decimals,
  suffix,
  emptyPlaceholder,
  onBlur,
  ...rest
}: NumberFieldProps): JSX.Element {
  const [focused, setFocused] = useState(false);
  const displayed =
    !focused && decimals !== undefined && value !== "" && /^-?\d+(\.\d+)?$/.test(value)
      ? Number(value).toLocaleString("es-CL", {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })
      : value;
  return (
    <TextInput
      inputMode="decimal"
      onBlur={(event) => {
        setFocused(false);
        onBlur?.(event);
      }}
      onChange={(event) => onValueChange(event.target.value)}
      onFocus={() => setFocused(true)}
      placeholder={emptyPlaceholder}
      suffix={suffix}
      type="text"
      value={displayed}
      {...rest}
    />
  );
}

/* ---------- Select / combobox ---------- */

export type SelectOption = { value: string; label: string; disabled?: boolean };

export type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[];
  /** Shown as a disabled first option — real hint, not a fake selection. */
  placeholder?: string;
  /** Message when the list carries no compatible option. */
  emptyMessage?: string;
  invalid?: boolean;
};

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(function SelectField(
  {
    options,
    placeholder,
    emptyMessage,
    invalid,
    className,
    id,
    "aria-describedby": describedBy,
    ...rest
  },
  ref,
) {
  const field = useFieldWiring(invalid);
  const described = [describedBy, field.describedBy].filter(Boolean).join(" ") || undefined;
  if (options.length === 0 && emptyMessage) {
    return (
      <span className="ui-field__input ui-select-empty" role="note">
        {emptyMessage}
      </span>
    );
  }
  return (
    <span className={`ui-select-wrap${field.invalid ? " is-invalid" : ""}`}>
      <select
        aria-describedby={described}
        aria-invalid={field.invalid || undefined}
        className={`ui-field__input ui-select ${className ?? ""}`}
        id={id ?? field.id}
        ref={ref}
        {...rest}
      >
        {placeholder ? (
          <option disabled value="">
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option disabled={option.disabled} key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <svg aria-hidden className="ui-select__chevron" height="10" viewBox="0 0 10 6" width="10">
        <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </span>
  );
});

/* ---------- misc ---------- */

export function Spinner({ label }: { label?: string }): JSX.Element {
  return <span aria-label={label ?? t("ui.loading")} className="ui-spinner" role="status" />;
}

/* ---------- Tooltip ---------- */

/** Tooltip — el nombre completo del control y su atajo, visibles al
 * hover/focus. Jamás sustituye a la etiqueta visible: la refuerza. */
export function Tooltip({
  label,
  shortcut,
  side = "top",
  children,
}: {
  label: string;
  shortcut?: string;
  side?: "top" | "bottom" | "left" | "right";
  children: ReactNode;
}): JSX.Element {
  const tipId = useId();
  return (
    <span className={`ui-tooltip ui-tooltip--${side}`}>
      <span className="ui-tooltip__anchor" aria-describedby={tipId}>
        {children}
      </span>
      <span className="ui-tooltip__tip" id={tipId} role="tooltip">
        {label}
        {shortcut ? <span className="ui-tooltip__key">{shortcut}</span> : null}
      </span>
    </span>
  );
}

/* ---------- IconButton / ButtonGroup ---------- */

export type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Nombre del comando — OBLIGATORIO como aria-label y como tooltip. Un
   * botón de ícono sin nombre es un botón ilegible. */
  label: string;
  /** Atajo documentado en el tooltip («Nombre — Atajo»). */
  shortcut?: string;
  variant?: ButtonVariant;
  icon: ReactNode;
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, shortcut, variant = "ghost", icon, className, ...rest },
  ref,
): JSX.Element {
  return (
    <Tooltip label={label} shortcut={shortcut}>
      <button
        aria-label={label}
        className={`ui-icon-button ${VARIANT_CLASS[variant]} ${className ?? ""}`.trim()}
        ref={ref}
        title={shortcut ? `${label} — ${shortcut}` : label}
        type="button"
        {...rest}
      >
        <span aria-hidden className="ui-icon-button__icon">
          {icon}
        </span>
      </button>
    </Tooltip>
  );
});

/** Agrupa acciones de una región. En desarrollo advierte si la región lleva
 * más de un botón primario — una región, una voz (§3.4 jerarquía). */
export function ButtonGroup({
  children,
  region = "ui-region",
}: {
  children: ReactNode;
  /** Nombre lógico de la región para el aviso de desarrollo. */
  region?: string;
}): JSX.Element {
  const primaries = Children.toArray(children).filter(
    (child) =>
      isValidElement(child) && (child as ReactElement<ButtonProps>).props.variant === "primary",
  ).length;
  useEffect(() => {
    if (import.meta.env.DEV && primaries > 1) {
      console.warn(
        `[ButtonGroup] ${primaries} botones primarios en la región «${region}» — esperado: 1.`,
      );
    }
  }, [primaries, region]);
  return (
    <div className="ui-button-group" role="group">
      {children}
    </div>
  );
}

/* ---------- MoneyField ---------- */

/** Campo de dinero — acepta «1.435.471», «1435471» y «1249,5»; formatea en
 * blur según la moneda (CLP entero, USD 2 dec, UF 4 dec). El valor guardado
 * es la cadena decimal canónica — nunca float. */
export function MoneyField({
  currency = "CLP",
  ...props
}: NumberFieldProps & { currency?: string }): JSX.Element {
  return (
    <NumberField
      decimals={moneyDigits(currency)}
      prefix={currency === "CLP" ? "$" : currency === "USD" ? "US$" : currency}
      {...props}
    />
  );
}

/* ---------- Checkbox / Radio / Switch / SegmentedControl ---------- */

export function Checkbox({
  label,
  hint,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }): JSX.Element {
  return (
    <label className="ui-check">
      <input className="ui-check__box" type="checkbox" {...rest} />
      <span aria-hidden className="ui-check__mark" />
      <span className="ui-check__text">
        {label}
        {hint ? <span className="ui-check__hint">{hint}</span> : null}
      </span>
    </label>
  );
}

export function Radio({
  label,
  hint,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }): JSX.Element {
  return (
    <label className="ui-check ui-check--radio">
      <input className="ui-check__box" type="radio" {...rest} />
      <span aria-hidden className="ui-check__mark" />
      <span className="ui-check__text">
        {label}
        {hint ? <span className="ui-check__hint">{hint}</span> : null}
      </span>
    </label>
  );
}

/** Interruptor binario — solo para efecto inmediato; lo que requiere
 * confirmación usa un Checkbox + botón. */
export function Switch({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: ReactNode;
  hint?: ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <label className={`ui-check ui-switch${disabled ? " is-disabled" : ""}`}>
      <input
        checked={checked}
        className="ui-check__box"
        disabled={disabled}
        onChange={(event) => onCheckedChange(event.target.checked)}
        role="switch"
        type="checkbox"
      />
      <span aria-hidden className="ui-switch__track">
        <span className="ui-switch__thumb" />
      </span>
      <span className="ui-check__text">
        {label}
        {hint ? <span className="ui-check__hint">{hint}</span> : null}
      </span>
    </label>
  );
}

/** Control segmentado — 2–5 opciones mutuamente excluyentes, todas visibles.
 * Implementado como radiogroup real: teclado y lector ven la semántica. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onValueChange,
  name,
}: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onValueChange: (value: T) => void;
  name?: string;
}): JSX.Element {
  const autoName = useId();
  return (
    <div className="ui-segmented" role="radiogroup">
      {options.map((option) => (
        <label className="ui-segmented__option" key={option.value}>
          <input
            checked={option.value === value}
            className="ui-segmented__input"
            name={name ?? autoName}
            onChange={() => onValueChange(option.value)}
            type="radio"
            value={option.value}
          />
          <span className="ui-segmented__label">{option.label}</span>
        </label>
      ))}
    </div>
  );
}

/* ---------- Combobox ---------- */

/** Lista con búsqueda — la misma intención que Select pero para listas
 * largas: filtra en vivo, conserva la etiqueta visible tras elegir. */
export function Combobox({
  options,
  value,
  onValueChange,
  placeholder,
  emptyMessage,
  invalid,
  id,
}: {
  options: SelectOption[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  emptyMessage?: string;
  invalid?: boolean;
  id?: string;
}): JSX.Element {
  const field = useFieldWiring(invalid);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selected = options.find((o) => o.value === value);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);
  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);
  const choose = (option: SelectOption) => {
    onValueChange(option.value);
    setOpen(false);
    setQuery("");
  };
  return (
    <div className={`ui-combo${field.invalid ? " is-invalid" : ""}`} ref={rootRef}>
      <input
        aria-activedescendant={open ? `${listId}-${filtered[active]?.value}` : undefined}
        aria-autocomplete="list"
        aria-controls={open ? listId : undefined}
        aria-describedby={field.describedBy}
        aria-expanded={open}
        aria-invalid={field.invalid || undefined}
        className="ui-field__input"
        id={id ?? field.id}
        onBlur={() => setOpen(false)}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((i) => Math.min(i + 1, filtered.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (event.key === "Enter" && open && filtered[active]) {
            event.preventDefault();
            choose(filtered[active]);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder={selected ? undefined : placeholder}
        role="combobox"
        type="text"
        value={open ? query : (selected?.label ?? query)}
      />
      {open ? (
        <ul className="ui-combo__list" id={listId} role="listbox">
          {filtered.length === 0 ? (
            <li className="ui-combo__empty">{emptyMessage ?? t("ui.paletteEmpty")}</li>
          ) : (
            filtered.map((option, index) => (
              <li
                aria-selected={option.value === value}
                className={`ui-combo__option${index === active ? " is-active" : ""}`}
                id={`${listId}-${option.value}`}
                key={option.value}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(option);
                }}
                onMouseEnter={() => setActive(index)}
                role="option"
              >
                {option.label}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
