"use client";
import React from "react";
import { formatCurrency } from "@/lib/data-generator";

interface KpiData {
  totalMachines: number;
  lineCount: number;
  atRiskCount: number;
  criticalCount: number;
  threshold: number;
  scheduledSlots: number;
  totalSlots: number;
  deferredCount: number;
  failureExposure: number;
  avoidedExposure: number;
}

interface KpiRowProps {
  data: KpiData;
}

export const KpiRow: React.FC<KpiRowProps> = ({ data }) => {
  return (
    <div className="panel bg-surface border border-border-normal overflow-hidden shadow-sm">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border-normal">
        {/* 1. Monitored Fleet */}
        <div className="p-5 sm:p-6 flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Fleet Monitored
          </div>
          <div className="mt-2 flex items-baseline gap-2.5">
            <span className="font-mono text-3xl sm:text-[32px] font-bold tracking-tight text-foreground tabular-nums">
              {data.totalMachines}
            </span>
            <span className="text-sm font-medium text-foreground-muted">
              units · {data.lineCount} lines
            </span>
          </div>
          <p className="mt-2 text-[13px] text-foreground-muted">
            All telemetry streams operational
          </p>
        </div>

        {/* 2. Requiring Attention */}
        <div className="p-5 sm:p-6 flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Requiring Attention
          </div>
          <div className="mt-2 flex items-baseline gap-2.5">
            <span className="font-mono text-3xl sm:text-[32px] font-bold tracking-tight text-foreground tabular-nums">
              {data.atRiskCount}
            </span>
            <span className="text-sm font-medium text-foreground-muted">
              units ≥ {Math.round(data.threshold * 100)}% threshold
            </span>
          </div>
          <p className="mt-2 text-[13px] text-foreground-muted">
            Exceeding calibrated alert cutoff
          </p>
        </div>

        {/* 3. High-Risk Critical */}
        <div className="p-5 sm:p-6 flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Active High-Risk Alerts
          </div>
          <div className="mt-2 flex items-baseline gap-2.5">
            <span className="font-mono text-3xl sm:text-[32px] font-bold tracking-tight text-status-critical tabular-nums">
              {data.criticalCount}
            </span>
            <span className="text-sm text-status-critical font-semibold">
              critical tier
            </span>
          </div>
          <p className="mt-2 text-[13px] text-foreground-muted">
            Immediate shift dispatch required
          </p>
        </div>

        {/* 4. Technician Capacity */}
        <div className="p-5 sm:p-6 flex flex-col justify-between">
          <div className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Available Technician Slots
          </div>
          <div className="mt-2 flex items-baseline gap-2.5">
            <span className="font-mono text-3xl sm:text-[32px] font-bold tracking-tight text-foreground tabular-nums">
              {data.scheduledSlots}
              <span className="text-foreground-muted text-xl font-normal">
                /{data.totalSlots}
              </span>
            </span>
            <span className="text-sm font-medium text-foreground-muted">
              assigned
            </span>
          </div>
          <p className="mt-2 text-[13px] text-foreground-muted">
            {data.deferredCount > 0 ? (
              <span className="text-status-warning font-semibold">
                {data.deferredCount} at-risk units deferred
              </span>
            ) : (
              <span className="text-accent-forest font-semibold">
                Full roster coverage
              </span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
};
