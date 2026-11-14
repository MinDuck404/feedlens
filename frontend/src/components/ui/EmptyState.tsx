import { type ReactNode } from "react";
import { Button } from "./Button";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: ReactNode;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

/**
 * EmptyState tinh giản chuẩn phong cách Paper của Uberdesigner
 * Dùng cho danh sách trống, kết quả lọc không tìm thấy, hoặc trang đầu tiên
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`paper-card flex flex-col items-center justify-center p-8 text-center sm:p-12 ${className}`}
    >
      {icon && (
        <div className="mb-4 grid size-12 place-items-center rounded-full border border-line bg-sunken text-ink-soft shadow-xs sm:size-14">
          {icon}
        </div>
      )}
      <h3 className="text-base font-semibold tracking-tight text-ink sm:text-lg">
        {title}
      </h3>
      {description && (
        <p className="mt-1.5 max-w-sm text-sm text-ink-soft leading-relaxed">
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          {action && (
            <Button
              variant="primary"
              size="md"
              icon={action.icon}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          )}
          {secondaryAction && (
            <Button
              variant="outline"
              size="md"
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
