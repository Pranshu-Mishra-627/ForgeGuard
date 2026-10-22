"use client";
import React from "react";
import { AlertCircle, ChevronRight } from "lucide-react";
import { Machine } from "@/lib/types";

interface CriticalBannerProps {
  criticalMachines: Machine[];
  statusById: Map<string, "scheduled" | "deferred">;
  onSelectMachine: (m: Machine) => void;
}

export const CriticalBanner: React.FC<CriticalBannerProps> = ({
  criticalMachines,
  statusById,
  onSelectMachine,
}) => {
  if (criticalMachines.length === 0) return null;

  const scheduledCount = criticalMachines.filter(
    (m) => statusById.get(m.id) === "scheduled"
  ).length;
  const deferredCount = criticalMachines.length - scheduledCount;

  return (
    <div
      role="alert"
      className="relative flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-[6px] border border-status-critical-border bg-status-critical-bg py-3.5 pl-5 pr-4 shadow-sm"
    >
      {/* Status indicator line */}
      <span
        className="absolute inset-y-0 left-0 w-[4px] rounded-l bg-status-critical"
        aria-hidden="true"
      />

      <div className="flex items-center gap-3">
        <AlertCircle className="size-5 text-status-critical shrink-0" />
        <p className="text-sm text-foreground">
          <span className="font-bold text-status-critical">
            {criticalMachines.length} critical machine{criticalMachines.length > 1 ? "s" : ""}
          </span>
          <span className="text-foreground-muted">
            {" — "}
            {deferredCount === 0
              ? "all allocated to technician slots this shift."
              : `${scheduledCount} scheduled, ${deferredCount} deferred due to capacity constraints.`}
          </span>
        </p>
      </div>

      <ul className="flex flex-wrap items-center gap-2" aria-label="Critical machines">
        {criticalMachines.slice(0, 4).map((m) => {
          const isSched = statusById.get(m.id) === "scheduled";
          return (
            <li key={m.id}>
              <button
                type="button"
                onClick={() => onSelectMachine(m)}
                className="group inline-flex h-8 items-center gap-2 rounded-[4px] border border-border-normal bg-surface px-3 font-mono text-xs text-foreground transition-colors hover:border-status-critical-border hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-critical shadow-sm"
              >
                <span
                  className={`size-2 rounded-full ${
                    isSched ? "bg-status-healthy" : "bg-status-warning"
                  }`}
                  aria-hidden="true"
                />
                <span className="font-bold">{m.id}</span>
                <span className="text-status-critical font-semibold">
                  {Math.round(m.probability * 100)}%
                </span>
                <ChevronRight className="size-3.5 text-foreground-muted transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                <span className="sr-only">Open details for {m.id}</span>
              </button>
            </li>
          );
        })}
        {criticalMachines.length > 4 && (
          <li className="px-1.5 font-mono text-xs font-medium text-foreground-muted">
            +{criticalMachines.length - 4} more
          </li>
        )}
      </ul>
    </div>
  );
};
