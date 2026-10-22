"use client";
import React from "react";
import { Users, Minus, Plus, AlertTriangle } from "lucide-react";
import { Machine } from "@/lib/types";
import { formatCurrency } from "@/lib/data-generator";

interface TechnicianAllocationProps {
  slots: number;
  onSlotsChange: (newSlots: number) => void;
  threshold: number;
  scheduledMachines: Machine[];
  deferredMachines: Machine[];
  reasonsById: Map<string, string>;
  unmitigatedExposure: number;
  onSelectMachine: (m: Machine) => void;
  className?: string;
  listHeight?: string;
}

export const TechnicianAllocation: React.FC<TechnicianAllocationProps> = ({
  slots,
  onSlotsChange,
  threshold,
  scheduledMachines,
  deferredMachines,
  reasonsById,
  unmitigatedExposure,
  onSelectMachine,
  className = "",
  listHeight = "max-h-[380px]",
}) => {
  const totalAlerts = scheduledMachines.length + deferredMachines.length;
  const idleSlots = Math.max(0, slots - scheduledMachines.length);

  return (
    <section className={`panel flex flex-col overflow-hidden shadow-sm ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between gap-4 border-b border-border-normal px-6 py-4.5">
        <div>
          <h2 className="text-[18px] font-bold tracking-tight text-foreground">
            Technician Allocation
          </h2>
          <p className="mt-1 text-[13px] text-foreground-muted">
            Capacity-constrained shift queue · {totalAlerts} unit{totalAlerts !== 1 ? "s" : ""} at or above{" "}
            {Math.round(threshold * 100)}% threshold
          </p>
        </div>
      </div>

      {/* Capacity Controls Area */}
      <div className="space-y-4 border-b border-border-normal bg-surface px-6 py-4">
        {/* Slot Stepper */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 text-[13.5px] text-foreground-muted">
            <Users className="size-4 text-foreground-muted" />
            <span className="font-semibold text-foreground">Active Technician Roster</span>
          </div>
          <div
            className="flex items-center rounded-[4px] border border-border-normal bg-surface-subtle shadow-sm"
            role="group"
            aria-label="Technician slots"
          >
            <button
              type="button"
              disabled={slots <= 0}
              onClick={() => onSlotsChange(Math.max(0, slots - 1))}
              aria-label="Remove technician slot"
              className="flex size-9 items-center justify-center text-foreground-muted transition-colors hover:bg-surface-hover hover:text-foreground disabled:opacity-30 disabled:pointer-events-none focus-visible:outline-none"
            >
              <Minus className="size-3.5" />
            </button>
            <output className="w-10 text-center font-mono text-sm font-bold tabular-nums text-foreground">
              {slots}
            </output>
            <button
              type="button"
              disabled={slots >= 16}
              onClick={() => onSlotsChange(Math.min(16, slots + 1))}
              aria-label="Add technician slot"
              className="flex size-9 items-center justify-center text-foreground-muted transition-colors hover:bg-surface-hover hover:text-foreground disabled:opacity-30 disabled:pointer-events-none focus-visible:outline-none"
            >
              <Plus className="size-3.5" />
            </button>
          </div>
        </div>

        {/* Capacity Visual Progress Bar */}
        <div className="flex gap-1.5" aria-hidden="true">
          {Array.from({ length: Math.max(1, slots) }).map((_, i) => {
            const isFilled = i < scheduledMachines.length;
            return (
              <span
                key={i}
                className={`h-2.5 flex-1 rounded-[2px] border ${
                  isFilled
                    ? "bg-accent-forest border-accent-forest-border"
                    : "bg-surface-subtle border-border-subtle"
                }`}
              />
            );
          })}
        </div>

        {/* Allocation Tally */}
        <div className="flex justify-between text-xs text-foreground-muted border-t border-border-subtle pt-2.5">
          <span>
            <span className="font-mono text-accent-forest font-bold">
              {scheduledMachines.length}
            </span>{" "}
            scheduled
          </span>
          <span>
            <span className="font-mono text-status-warning font-bold">
              {deferredMachines.length}
            </span>{" "}
            deferred
          </span>
          <span>
            <span className="font-mono text-foreground font-bold">{idleSlots}</span> idle
          </span>
        </div>

        {/* Capacity Exhaustion Alert Banner */}
        {deferredMachines.length > 0 && (
          <div
            role="alert"
            className="flex gap-2.5 rounded-[4px] border border-status-warning-border bg-status-warning-bg p-3 text-xs text-foreground"
          >
            <AlertTriangle className="size-4 shrink-0 mt-0.5 text-status-warning" />
            <p className="leading-snug">
              <span className="font-bold text-status-warning">
                {deferredMachines.length} at-risk unit{deferredMachines.length > 1 ? "s" : ""} deferred
              </span>{" "}
              representing <span className="font-mono font-bold text-foreground">{formatCurrency(unmitigatedExposure)}</span> unmitigated exposure.
            </p>
          </div>
        )}
      </div>

      {/* Queue List */}
      <div className={`flex-1 overflow-auto ${listHeight}`}>
        {totalAlerts === 0 ? (
          <div className="py-12 text-center text-sm text-foreground-muted">
            No machines above the {Math.round(threshold * 100)}% threshold.
          </div>
        ) : (
          <ol className="divide-y divide-border-subtle bg-surface">
            {scheduledMachines.map((m, idx) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => onSelectMachine(m)}
                  className="group flex w-full items-center gap-3.5 px-5 py-3 text-left transition-colors hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none"
                >
                  <span className="w-6 font-mono text-xs tabular-nums text-foreground-muted font-semibold">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[14px] font-bold text-foreground">
                        {m.id}
                      </span>
                      <span className="text-xs font-mono uppercase text-foreground-muted">
                        {m.type}
                      </span>
                    </div>
                    <p className="truncate text-[12.5px] text-foreground-muted mt-0.5" title={reasonsById.get(m.id)}>
                      {m.reason}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="rounded-[3px] px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-status-healthy bg-status-healthy-bg border border-status-healthy-border font-semibold">
                      Scheduled
                    </span>
                    <span className="font-mono text-xs font-medium text-foreground-muted">
                      Score {m.priority}
                    </span>
                  </div>
                </button>
              </li>
            ))}

            {/* Capacity Cutoff Separator */}
            {deferredMachines.length > 0 && (
              <li
                className="flex items-center gap-2 bg-surface-subtle px-5 py-2 text-foreground-muted"
                aria-hidden="true"
              >
                <span className="h-px flex-1 bg-border-normal" />
                <span className="eyebrow text-xs text-status-warning font-semibold">
                  Capacity Limit Cutoff ({slots} Slots Available)
                </span>
                <span className="h-px flex-1 bg-border-normal" />
              </li>
            )}

            {deferredMachines.map((m, idx) => (
              <li key={m.id} className="opacity-80 hover:opacity-100">
                <button
                  type="button"
                  onClick={() => onSelectMachine(m)}
                  className="group flex w-full items-center gap-3.5 px-5 py-3 text-left transition-colors hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none"
                >
                  <span className="w-6 font-mono text-xs tabular-nums text-foreground-muted font-semibold">
                    {String(scheduledMachines.length + idx + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[14px] font-bold text-foreground">
                        {m.id}
                      </span>
                      <span className="text-xs font-mono uppercase text-foreground-muted">
                        {m.type}
                      </span>
                    </div>
                    <p className="truncate text-[12.5px] text-foreground-muted mt-0.5" title={reasonsById.get(m.id)}>
                      {m.reason}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="rounded-[3px] px-2 py-0.5 font-mono text-xs uppercase tracking-wider text-status-warning bg-status-warning-bg border border-status-warning-border font-semibold">
                      Deferred
                    </span>
                    <span className="font-mono text-xs font-medium text-foreground-muted">
                      Score {m.priority}
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
};
