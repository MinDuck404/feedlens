import { Check, ChevronDown } from "lucide-react";
import { Children, forwardRef, isValidElement, useEffect, useId, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type ChangeEventHandler, type KeyboardEvent, type ReactElement, type ReactNode } from "react";
import { createPortal } from "react-dom";

type SelectOption = { value: string; label: ReactNode; disabled: boolean };
type SelectSize = "sm" | "md" | "lg";
type SelectProps = {
  className?: string;
  size?: SelectSize;
  shape?: "rounded" | "pill";
  id?: string;
  name?: string;
  form?: string;
  title?: string;
  disabled?: boolean;
  required?: boolean;
  value?: string;
  defaultValue?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean | "true" | "false" | "grammar" | "spelling";
  children?: ReactNode;
  onChange?: ChangeEventHandler<HTMLSelectElement>;
};

const SIZE_CLASSES: Record<SelectSize, string> = {
  sm: "h-9 min-h-11 px-3 py-1.5 text-sm sm:min-h-9",
  md: "h-11 min-h-11 px-3 py-2 text-sm",
  lg: "h-[52px] min-h-[52px] px-4 py-3 text-base",
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = "", size = "md", shape = "rounded", children, value, defaultValue, onChange, disabled, id, title, name, required, form, "aria-label": ariaLabel, "aria-labelledby": ariaLabelledby, "aria-describedby": ariaDescribedby, "aria-invalid": ariaInvalid },
  forwardedRef,
) {
  const options = useMemo(() => Children.toArray(children)
    .filter((child): child is ReactElement<{ value?: string | number; disabled?: boolean; children?: ReactNode }> => isValidElement(child) && child.type === "option")
    .map((option) => ({
      value: String(option.props.value ?? option.props.children ?? ""),
      label: option.props.children,
      disabled: !!option.props.disabled,
    })), [children]);
  const selectRef = useRef<HTMLSelectElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);
  const typeahead = useRef("");
  const typeaheadTimer = useRef<number | undefined>(undefined);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [internalValue, setInternalValue] = useState(String(defaultValue ?? options[0]?.value ?? ""));
  const [position, setPosition] = useState<{ left: number; width: number; top?: number; bottom?: number; maxHeight: number } | null>(null);
  const selectedValue = value === undefined ? internalValue : String(value);
  const selectedIndex = options.findIndex((option) => option.value === selectedValue);
  const selected = options[selectedIndex];

  useImperativeHandle(forwardedRef, () => selectRef.current as HTMLSelectElement);

  const enabledIndex = (start: number, direction: 1 | -1) => {
    for (let index = start; index >= 0 && index < options.length; index += direction) {
      if (!options[index].disabled) return index;
    }
    return -1;
  };

  const openMenu = (index = selectedIndex) => {
    const next = index >= 0 && !options[index]?.disabled ? index : enabledIndex(index < 0 ? 0 : index, 1);
    setActiveIndex(next);
    setOpen(true);
  };

  const closeMenu = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  };

  const choose = (option: SelectOption) => {
    if (disabled || option.disabled) return;
    if (value === undefined) setInternalValue(option.value);
    const select = selectRef.current;
    if (select) {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set?.call(select, option.value);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    closeMenu(true);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.defaultPrevented || disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      if (!open) openMenu(direction === 1 ? selectedIndex : enabledIndex(options.length - 1, -1));
      else setActiveIndex((current) => {
        const start = current < 0 ? (direction === 1 ? 0 : options.length - 1) : current + direction;
        return enabledIndex(start < 0 ? options.length - 1 : start >= options.length ? 0 : start, direction);
      });
      return;
    }
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setActiveIndex(enabledIndex(event.key === "Home" ? 0 : options.length - 1, event.key === "Home" ? 1 : -1));
      if (!open) setOpen(true);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation(); // Esc chỉ đóng danh sách, không đóng Dialog/Sheet cha
      closeMenu(true);
      return;
    }
    if (event.key === "Tab" && open) {
      closeMenu();
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault();
      const option = options[activeIndex];
      if (option) choose(option);
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && !open) {
      event.preventDefault();
      openMenu();
      return;
    }
    if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
      typeahead.current += event.key.toLocaleLowerCase();
      window.clearTimeout(typeaheadTimer.current);
      typeaheadTimer.current = window.setTimeout(() => { typeahead.current = ""; }, 700);
      const start = selectedIndex >= 0 ? selectedIndex + 1 : 0;
      const order = [...options.slice(start), ...options.slice(0, start)];
      const found = order.find((option) => !option.disabled && String(option.label ?? "").toLocaleLowerCase().startsWith(typeahead.current));
      if (found) {
        const index = options.indexOf(found);
        setActiveIndex(index);
        if (!open) setOpen(true);
      }
    }
  };

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const gap = 4;
    const spaceBelow = window.innerHeight - rect.bottom - gap - 8;
    const spaceAbove = rect.top - gap - 8;
    const flip = spaceBelow < 256 && spaceAbove > spaceBelow;
    const available = Math.max(80, Math.min(256, flip ? spaceAbove : spaceBelow));
    setPosition({
      left: rect.left,
      width: rect.width,
      maxHeight: available,
      ...(flip ? { bottom: window.innerHeight - rect.top + gap } : { top: rect.bottom + gap }),
    });
  }, [open]);

  useLayoutEffect(() => {
    if (!open || activeIndex < 0) return;
    document.getElementById(`${listboxId}-option-${activeIndex}`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, listboxId, open]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!triggerRef.current?.contains(target) && !listboxRef.current?.contains(target)) closeMenu();
    };
    const onResize = () => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      const gap = 4;
      const spaceBelow = window.innerHeight - rect.bottom - gap - 8;
      const spaceAbove = rect.top - gap - 8;
      const flip = spaceBelow < 256 && spaceAbove > spaceBelow;
      setPosition({ left: rect.left, width: rect.width, maxHeight: Math.max(80, Math.min(256, flip ? spaceAbove : spaceBelow)), ...(flip ? { bottom: window.innerHeight - rect.top + gap } : { top: rect.bottom + gap }) });
    };
    const onScroll = (event: Event) => {
      if (listboxRef.current?.contains(event.target as Node)) return;
      closeMenu();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  const optionList = open && position && createPortal(
    <div ref={listboxRef} id={listboxId} role="listbox" aria-label={ariaLabel} aria-labelledby={ariaLabelledby}
      className="fixed z-[100] overflow-y-auto rounded-xl border border-[var(--field-line)] bg-surface p-1 shadow-lg"
      style={{ left: position.left, width: position.width, top: position.top, bottom: position.bottom, maxHeight: position.maxHeight }}>
      {options.map((option, index) => <div key={`${option.value}-${index}`} id={`${listboxId}-option-${index}`} role="option" aria-selected={selectedValue === option.value} aria-disabled={option.disabled || undefined}
        onMouseEnter={() => !option.disabled && setActiveIndex(index)} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(option)}
        className={`flex min-h-11 items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-ink ${option.disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"} ${activeIndex === index ? "bg-sunken" : "hover:bg-sunken"}`}>
        <span className="min-w-0 truncate">{option.label}</span>
        {selectedValue === option.value && <Check aria-hidden="true" className="size-4 shrink-0 text-accent" />}
      </div>)}
    </div>, document.body,
  );

  return <span className={`relative block min-w-0 flex-1 ${className}`}>
    <select ref={selectRef} name={name} form={form} required={required} disabled={disabled} value={selectedValue} onChange={onChange} tabIndex={-1} aria-hidden="true" className="sr-only">
      {children}
    </select>
    <button ref={triggerRef} id={id} title={title} type="button" disabled={disabled} aria-label={ariaLabel} aria-labelledby={ariaLabelledby} aria-describedby={ariaDescribedby} aria-invalid={ariaInvalid} aria-required={required || undefined} role="combobox" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listboxId : undefined}
      aria-activedescendant={open && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
      className={`field flex w-full min-w-0 items-center justify-between gap-3 text-left ${SIZE_CLASSES[size]} ${shape === "pill" ? "rounded-full" : "rounded-[var(--radius-field)]"} disabled:cursor-not-allowed disabled:opacity-60`}
      onKeyDown={handleKeyDown} onClick={() => open ? closeMenu() : openMenu()}>
      <span className="min-w-0 truncate">{selected?.label ?? ""}</span>
      <ChevronDown aria-hidden="true" className={`size-4 shrink-0 text-ink-soft transition-transform ${open ? "rotate-180" : ""}`} />
    </button>
    {optionList}
  </span>;
});
Select.displayName = "Select";
