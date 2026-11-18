import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { wrapperClassName?: string };

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className = "", wrapperClassName = "", children, ...props }, ref) => <span className={`relative block min-w-0 flex-1 ${wrapperClassName}`}>
    <select ref={ref} {...props} className={`field h-11 appearance-none pr-10 ${className}`}>{children}</select>
    <ChevronDown aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-ink-soft" />
  </span>,
);
Select.displayName = "Select";
