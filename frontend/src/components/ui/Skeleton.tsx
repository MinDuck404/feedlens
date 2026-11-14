import type { CSSProperties } from "react";

export interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: "sm" | "md" | "lg" | "xl" | "2xl" | "full";
  circle?: boolean;
  label?: string;
  "aria-label"?: string;
}

const ROUNDED_MAP = {
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  xl: "rounded-xl",
  "2xl": "rounded-2xl",
  full: "rounded-full",
};

/**
 * Skeleton Primitive với hiệu ứng Shimmer Wave mượt mà
 */
export function Skeleton({
  className = "",
  width,
  height,
  rounded = "md",
  circle = false,
  label,
  "aria-label": ariaLabel,
}: SkeletonProps) {
  const style: CSSProperties = {
    width: width,
    height: height,
  };

  const accessibleLabel = ariaLabel || label;

  return (
    <div
      {...(accessibleLabel
        ? { role: "status", "aria-label": accessibleLabel }
        : { "aria-hidden": "true" })}
      style={style}
      className={`skeleton-shimmer select-none ${
        circle ? "rounded-full aspect-square" : ROUNDED_MAP[rounded]
      } ${className}`}
    />
  );
}

/**
 * Skeleton cho dòng văn bản nhiều hàng
 */
export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2.5 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="14px"
          className={
            i === lines - 1
              ? "w-2/3"
              : i === 0
              ? "w-full"
              : i % 2 === 0
              ? "w-4/5"
              : "w-11/12"
          }
        />
      ))}
    </div>
  );
}

/**
 * Skeleton Card mô phỏng thẻ bài viết hoặc kết quả chạy
 */
export function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={`paper-card p-4 space-y-3 ${className}`}>
      <div className="flex items-center gap-3">
        <Skeleton circle width="36px" height="36px" />
        <div className="flex-1 space-y-1.5">
          <Skeleton height="14px" className="w-1/3" />
          <Skeleton height="10px" className="w-1/4" />
        </div>
      </div>
      <SkeletonText lines={2} />
      <div className="pt-2 flex justify-between items-center">
        <Skeleton height="12px" className="w-20" rounded="full" />
        <Skeleton height="28px" className="w-16" rounded="full" />
      </div>
    </div>
  );
}
