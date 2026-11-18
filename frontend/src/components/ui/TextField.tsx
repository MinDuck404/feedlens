import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

type FieldSize = "sm" | "md" | "lg";
type FieldShape = "rounded" | "pill";
type FieldFrameProps = {
  size?: FieldSize;
  shape?: FieldShape;
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
};
type InputProps = FieldFrameProps & { as?: "input" } & Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "className">;
type TextareaProps = FieldFrameProps & { as: "textarea" } & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "className">;

const SIZE_CLASSES: Record<FieldSize, string> = {
  sm: "h-9 min-h-11 px-3 py-1.5 text-sm sm:min-h-9",
  md: "min-h-11 px-3 py-2 text-sm",
  lg: "h-[52px] min-h-[52px] px-4 py-3 text-base",
};

export function TextField(props: InputProps | TextareaProps) {
  const generatedId = useId();
  const {
    as,
    className = "",
    size = "md",
    shape = "rounded",
    label,
    hint,
    error,
    id = generatedId,
    ...fieldProps
  } = props;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [fieldProps["aria-describedby"], hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  const fieldClassName = `field ${SIZE_CLASSES[size]} ${shape === "pill" ? "rounded-full" : "rounded-[var(--radius-field)]"} ${className}`;
  const field = as === "textarea"
    ? <textarea {...fieldProps as TextareaHTMLAttributes<HTMLTextAreaElement>} id={id} className={fieldClassName} aria-describedby={describedBy} aria-invalid={error ? true : fieldProps["aria-invalid"]} />
    : <input {...fieldProps as InputHTMLAttributes<HTMLInputElement>} id={id} className={fieldClassName} aria-describedby={describedBy} aria-invalid={error ? true : fieldProps["aria-invalid"]} />;

  return <div className="min-w-0">
    {label != null && <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>}
    {field}
    {hint != null && <p id={hintId} className="mt-1.5 text-xs leading-relaxed text-ink-soft">{hint}</p>}
    {error != null && <p id={errorId} role="alert" className="mt-1.5 text-xs leading-relaxed text-danger">{error}</p>}
  </div>;
}
