import type { ConfigField } from "../../lib/types.ts";
import styles from "./ConfigForm.module.css";

function fieldValue(field: ConfigField, values: Record<string, unknown>): unknown {
  return values[field.key] ?? field.default ?? "";
}

/** Schema-driven configuration editor for one catalog component. */
export function ConfigForm({
  schema,
  values,
  onChange,
  disabled,
}: {
  schema: ConfigField[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
}) {
  if (schema.length === 0) {
    return <p className={styles.empty}>This component exposes no configuration fields.</p>;
  }
  return (
    <div className={styles.form}>
      {schema.map((field) => {
        const value = fieldValue(field, values);
        const label = `${field.label}${field.unit ? ` (${field.unit})` : ""}${field.required ? " *" : ""}`;
        return (
          <label key={field.key} className={styles.field}>
            {label}
            {field.type === "enum" ? (
              <select
                value={String(value ?? "")}
                onChange={(event) => onChange(field.key, event.target.value)}
                disabled={disabled}
              >
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : field.type === "boolean" ? (
              <input
                type="checkbox"
                checked={value === true}
                onChange={(event) => onChange(field.key, event.target.checked)}
                disabled={disabled}
              />
            ) : field.type === "number" ? (
              <input
                value={String(value ?? "")}
                inputMode="decimal"
                autoComplete="off"
                spellCheck={false}
                disabled={disabled}
                onChange={(event) => {
                  const text = event.target.value.trim();
                  if (text === "") {
                    onChange(field.key, field.default ?? 0);
                    return;
                  }
                  const parsed = Number(text);
                  if (!Number.isNaN(parsed)) onChange(field.key, parsed);
                }}
              />
            ) : (
              <input
                value={String(value ?? "")}
                autoComplete="off"
                spellCheck={false}
                disabled={disabled}
                onChange={(event) => onChange(field.key, event.target.value)}
              />
            )}
            {field.description ? (
              <span className={styles.description}>{field.description}</span>
            ) : null}
          </label>
        );
      })}
    </div>
  );
}
