import {
  forwardRef,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

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
      {/* The control must carry id=fieldId and, when present,
          aria-describedby={`${helpId} ${errorId}`} / aria-invalid. The
          wrapped inputs below wire this automatically via FieldContext-free
          convention: pass the ids down through clone-free props. */}
      {children}
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
  { suffix, prefix, invalid, className, ...rest },
  ref,
): JSX.Element {
  if (suffix || prefix) {
    return (
      <span className={`ui-input-affix${invalid ? " is-invalid" : ""}`}>
        {prefix ? <span className="ui-input-affix__part">{prefix}</span> : null}
        <input
          aria-invalid={invalid || undefined}
          className={`ui-field__input ui-field__input--bare ${className ?? ""}`}
          ref={ref}
          {...rest}
        />
        {suffix ? <span className="ui-input-affix__part">{suffix}</span> : null}
      </span>
    );
  }
  return (
    <input
      aria-invalid={invalid || undefined}
      className={`ui-field__input ${className ?? ""}`}
      ref={ref}
      {...rest}
    />
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
  { options, placeholder, emptyMessage, invalid, className, ...rest },
  ref,
) {
  if (options.length === 0 && emptyMessage) {
    return (
      <span className="ui-field__input ui-select-empty" role="note">
        {emptyMessage}
      </span>
    );
  }
  return (
    <span className={`ui-select-wrap${invalid ? " is-invalid" : ""}`}>
      <select
        aria-invalid={invalid || undefined}
        className={`ui-field__input ui-select ${className ?? ""}`}
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
