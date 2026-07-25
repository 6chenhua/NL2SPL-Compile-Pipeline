import type { ReactNode } from "react";

interface StateViewProps {
  title: string;
  children?: ReactNode;
  tone?: "neutral" | "warning" | "error" | "success";
  compact?: boolean;
}

export function StateView({
  title,
  children,
  tone = "neutral",
  compact = false,
}: StateViewProps) {
  return (
    <div className={`state-view state-view--${tone}${compact ? " state-view--compact" : ""}`}>
      <strong>{title}</strong>
      {children ? <div className="state-view__body">{children}</div> : null}
    </div>
  );
}

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const tone = normalized.includes("error") ||
    normalized.includes("failed") ||
    normalized === "not_accepted"
    ? "error"
    : normalized.includes("unavailable") ||
        normalized.includes("pending") ||
        normalized.includes("assumed") ||
        normalized.includes("ambiguous") ||
        normalized.includes("generating")
      ? "warning"
      : normalized.includes("available") ||
          normalized === "ready" ||
          normalized === "direct" ||
          normalized === "source_backed" ||
          normalized === "complete" ||
          normalized === "accepted" ||
          normalized === "applied" ||
          normalized === "preview_ready"
        ? "success"
        : "neutral";

  return <span className={`status-badge status-badge--${tone}`}>{value}</span>;
}

export function formatError(error: unknown): string {
  if (error instanceof Error) {
    const code = "code" in error && typeof error.code === "string" ? ` (${error.code})` : "";
    return `${error.message}${code}`;
  }
  return "An unexpected error occurred.";
}
