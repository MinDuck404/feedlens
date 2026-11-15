import { useId, useLayoutEffect, useRef, useState } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  label: string;
  mode?: "radio" | "tabs";
  id?: string;
  compact?: boolean;
}

export function SegmentedControl({ value, onChange, options, label, mode = "radio", id, compact = false }: Props) {
  const generatedId = useId();
  const prefix = id ?? generatedId;
  const group = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState({ x: 0, y: 0, width: 0, height: 0 });
  const labels = options.map((o) => o.label).join("|");
  useLayoutEffect(() => {
    const root = group.current;
    if (!root) return;
    const measure = () => {
      const button = [...root.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.dataset.value === value);
      if (button) {
        const height = compact ? Math.min(36, button.offsetHeight - 4) : button.offsetHeight;
        setIndicator({ x: button.offsetLeft + (compact ? 2 : 0), y: button.offsetTop + (button.offsetHeight - height) / 2, width: button.offsetWidth - (compact ? 4 : 0), height });
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    document.fonts.ready.then(measure);
    return () => observer.disconnect();
  }, [value, labels, compact]);
  return <div className={mode === "tabs" ? "max-w-full overflow-x-auto pb-1" : "min-w-0"}>
    <div ref={group} role={mode === "tabs" ? "tablist" : "radiogroup"} aria-label={label}
      className={`relative border border-[var(--field-line)] bg-[var(--field-bg)] ${compact ? "gap-0.5 rounded-xl p-0.5" : "gap-1 rounded-2xl p-1"} ${mode === "tabs" ? "flex w-max min-w-full" : `grid ${options.length > 3 ? "grid-cols-2 sm:grid-cols-4" : options.length === 3 ? "grid-cols-3" : "grid-cols-2"}`}`}>
      <span aria-hidden="true" className="pointer-events-none absolute top-0 left-0 rounded-xl bg-primary transition-transform duration-[var(--duration-normal)] ease-[var(--ease-micro)] motion-reduce:transition-none"
        style={{ width: indicator.width, height: indicator.height, transform: `translate(${indicator.x}px, ${indicator.y}px)` }} />
      {options.map((option, index) => <button key={option.value} type="button" data-value={option.value}
        id={`${prefix}-tab-${option.value}`} role={mode === "tabs" ? "tab" : "radio"}
        aria-selected={mode === "tabs" ? value === option.value : undefined}
        aria-checked={mode === "radio" ? value === option.value : undefined}
        aria-controls={mode === "tabs" ? `${prefix}-panel-${option.value}` : undefined}
        tabIndex={value === option.value ? 0 : -1}
        onClick={() => onChange(option.value)}
        onKeyDown={(event) => {
          let next = index;
          if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % options.length;
          else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index + options.length - 1) % options.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = options.length - 1;
          else return;
          event.preventDefault(); onChange(options[next].value);
          group.current?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
        }}
        className={`relative z-10 min-h-11 min-w-0 rounded-xl text-center text-xs leading-snug transition-colors duration-[var(--duration-fast)] motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 ${compact ? "px-1.5 py-1 sm:min-h-10" : "px-2 py-2 sm:text-sm"} ${mode === "tabs" ? "flex-1 whitespace-nowrap px-3" : ""} ${value === option.value ? "font-semibold text-primary-ink" : "text-ink-soft hover:text-ink"}`}>
        {option.label}
      </button>)}
    </div>
  </div>;
}
