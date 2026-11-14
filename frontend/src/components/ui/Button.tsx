import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger" | "accent";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  busy?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  children?: ReactNode;
  pill?: boolean;
}

const VARIANT_MAP: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-ink hover:opacity-90 border border-transparent shadow-sm",
  secondary: "bg-sunken text-ink hover:bg-sunken-hover border border-transparent",
  outline: "border border-line bg-surface text-ink hover:border-ink hover:bg-surface shadow-xs",
  ghost: "text-ink-soft hover:text-ink hover:bg-sunken border border-transparent",
  danger: "bg-danger text-white hover:opacity-90 border border-transparent shadow-sm",
  accent: "bg-accent text-accent-ink hover:opacity-90 border border-transparent shadow-sm",
};

const SIZE_MAP: Record<ButtonSize, string> = {
  sm: "px-3 py-1 text-xs min-h-[30px]",
  md: "px-4 py-2 text-sm min-h-[38px]",
  lg: "px-5 py-2.5 text-base min-h-[46px]",
};

/**
 * Button dùng chung cho FeedLens
 * Hỗ trợ xúc giác mượt mà (scale khi hover/tap), spinner khi loading và accessible disabled state.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      busy = false,
      disabled = false,
      icon,
      iconRight,
      children,
      pill = true,
      className = "",
      type = "button",
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || busy;

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-busy={busy}
        className={`inline-flex items-center justify-center font-semibold select-none interactive-tap outline-none focus:outline-none focus:ring-0 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:pointer-events-none ${
          !busy && disabled
            ? "bg-sunken text-ink-faint border border-line shadow-none cursor-not-allowed"
            : `${VARIANT_MAP[variant]} ${busy ? "opacity-80" : ""}`
        } ${SIZE_MAP[size]} ${pill ? "rounded-full" : "rounded-xl"} ${className}`}
        {...props}
      >
        {busy ? (
          <Loader2 className="mr-1.5 size-4 shrink-0 animate-spin" />
        ) : icon ? (
          <span className="shrink-0">{icon}</span>
        ) : null}
        {children && <span className="truncate">{children}</span>}
        {!busy && iconRight && <span className="ml-1.5 shrink-0">{iconRight}</span>}
      </button>
    );
  }
);
Button.displayName = "Button";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label"?: string;
  label?: string;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  busy?: boolean;
  children?: ReactNode;
}

const ICON_SIZE_MAP: Record<"sm" | "md" | "lg", string> = {
  sm: "size-7",
  md: "size-8.5",
  lg: "size-10",
};

/**
 * IconButton dành riêng cho các hành động icon-only (hỗ trợ label/aria-label và icon/children)
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      "aria-label": ariaLabelProp,
      label,
      icon,
      variant = "ghost",
      size = "md",
      busy = false,
      disabled = false,
      children,
      className = "",
      type = "button",
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || busy;
    const ariaLabel = ariaLabelProp || label || "";
    const content = icon || children;

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-label={ariaLabel}
        title={ariaLabel}
        aria-busy={busy}
        className={`grid place-items-center rounded-full select-none interactive-tap outline-none focus:outline-none focus:ring-0 focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:pointer-events-none ${
          !busy && disabled
            ? "text-ink-faint/40 border border-transparent shadow-none"
            : `${VARIANT_MAP[variant]} ${busy ? "opacity-80" : ""}`
        } ${ICON_SIZE_MAP[size]} ${className}`}
        {...props}
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : content}
      </button>
    );
  }
);
IconButton.displayName = "IconButton";
