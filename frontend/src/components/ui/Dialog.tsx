import { X as XIcon } from "lucide-react";
import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** "right" cho Sheet trượt phải, "left" cho Mobile Drawer trượt trái, "center" cho Modal giữa màn hình */
  side?: "right" | "left" | "center";
  /** Chiều rộng tối đa của container (mặc định max-w-md) */
  maxWidth?: string;
  className?: string;
  contentClassName?: string;
  ariaLabel?: string;
  closeAriaLabel?: string;
  footer?: ReactNode;
  /** Khi cung cấp onSubmit, container dialog sẽ render thành thẻ <form> */
  onSubmit?: (e: React.FormEvent) => void;
}

/**
 * Dialog / Sheet Component dùng chung cho toàn bộ FeedLens
 * 
 * Tính năng chính (Đáp ứng đầy đủ Code-audit #5 & Motion system):
 * 1. Exit animation mượt mà (chờ animation kết thúc mới unmount)
 * 2. Focus trap hoàn chỉnh (Tab / Shift+Tab giữ focus trong dialog)
 * 3. Restore focus về nút đã bấm mở sau khi đóng
 * 4. Thoát an toàn bằng phím Escape (ngăn chặn đóng chồng nhiều panel)
 * 5. Khóa cuộn màn hình nền (Scroll Lock)
 * 6. Đóng khi click ngoài vùng nội dung (Backdrop click)
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  side = "right",
  maxWidth = "max-w-md",
  className = "",
  contentClassName = "flex-1 space-y-6 overflow-x-hidden overflow-y-auto px-6 py-5",
  ariaLabel,
  closeAriaLabel = "Đóng",
  footer,
  onSubmit,
}: DialogProps) {
  const titleId = useId();
  const accessibleName = ariaLabel || (typeof title === "string" ? title : undefined);

  // Trạng thái lifecycle cho animation ra (exit animation)
  const [isRendered, setIsRendered] = useState(open);
  const [isClosing, setIsClosing] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Xử lý mở / đóng có animation
  useEffect(() => {
    if (open) {
      previousActiveElement.current = document.activeElement as HTMLElement | null;
      setIsRendered(true);
      setIsClosing(false);
    } else if (isRendered) {
      setIsClosing(true);
      const timer = window.setTimeout(() => {
        setIsRendered(false);
        setIsClosing(false);

        const prev = previousActiveElement.current;
        const activeDialog = document.activeElement?.closest('[role="dialog"]');
        const activeInAnotherDialog = activeDialog && activeDialog !== containerRef.current;

        if (
          prev &&
          document.contains(prev) &&
          !activeInAnotherDialog &&
          typeof prev.focus === "function"
        ) {
          prev.focus({ preventScroll: true });
        }
      }, 180); // Khớp với --duration-fast (160-180ms)
      return () => clearTimeout(timer);
    }
  }, [open, isRendered]);

  // Khóa cuộn trang khi mở
  useEffect(() => {
    if (!isRendered) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isRendered]);

  // Bắt phím Escape và Focus Trap
  useEffect(() => {
    if (!isRendered || isClosing) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (e.defaultPrevented) return; // control con (vd. Select đang mở) đã xử lý Esc
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (e.key === "Tab" && containerRef.current) {
        const focusable = [...containerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )].filter((element) => element.getClientRects().length > 0 && !element.closest("[hidden]"));
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRendered, isClosing]);

  // Tự động focus vào dialog khi render xong
  useEffect(() => {
    if (isRendered && !isClosing && containerRef.current) {
      // Tìm phần tử có autoFocus hoặc phần tử focusable đầu tiên
      const auto = containerRef.current.querySelector<HTMLElement>("[autofocus]");
      if (auto && auto.getClientRects().length) {
        auto.focus();
      } else {
        const first = [...containerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )].find((element) => element.getClientRects().length > 0 && !element.closest("[hidden]"));
        if (first) first.focus();
      }
    }
  }, [isRendered, isClosing]);

  const handleBackdropMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget && !isClosing) {
      onCloseRef.current();
    }
  }, [isClosing]);

  if (!isRendered) return null;

  const isSheetRight = side === "right";
  const isSheetLeft = side === "left";
  const isSheet = isSheetRight || isSheetLeft;
  const ContainerTag = onSubmit ? "form" : "div";

  const justifyClass = isSheetRight ? "justify-end" : isSheetLeft ? "justify-start" : "items-center justify-center p-4";
  const animationClass = isSheetRight
    ? (isClosing ? "sheet-exit" : "sheet")
    : isSheetLeft
    ? (isClosing ? "sheet-left-exit" : "sheet-left")
    : (isClosing ? "dialog-modal-out" : "dialog-modal-in");
  const borderClass = isSheetRight
    ? "border-l border-line"
    : isSheetLeft
    ? "border-r border-line"
    : "rounded-2xl border border-line";

  return (
    <div
      role="presentation"
      className={`fixed inset-0 z-50 flex bg-ink/35 ${justifyClass} ${
        isClosing ? "backdrop-out" : "backdrop-in"
      }`}
      onMouseDown={handleBackdropMouseDown}
    >
      <ContainerTag
        ref={containerRef as any}
        onSubmit={onSubmit}
        role="dialog"
        aria-modal="true"
        aria-label={accessibleName}
        aria-labelledby={accessibleName ? undefined : titleId}
        className={`flex min-h-0 flex-col bg-surface shadow-2xl ${
          isSheet ? `h-full w-full ${maxWidth}` : `w-full ${maxWidth}`
        } ${animationClass} ${borderClass} ${className}`}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-line px-6 py-4">
          <div className="min-w-0 pr-2">
            <h2 id={titleId} className="truncate text-lg font-semibold tracking-tight text-ink">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-xs text-ink-soft">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={closeAriaLabel}
            className="grid size-8 shrink-0 place-items-center rounded-lg text-ink-soft transition-colors hover:bg-sunken hover:text-ink active:scale-95 outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <XIcon className="size-5" />
          </button>
        </header>

        <div className={`min-h-0 ${contentClassName}`}>
          {children}
        </div>

        {footer && (
          <footer className="shrink-0 border-t border-line px-6 py-4">
            {footer}
          </footer>
        )}
      </ContainerTag>
    </div>
  );
}

/** Alias thuận tiện cho Sheet Drawer */
export const Sheet = Dialog;
