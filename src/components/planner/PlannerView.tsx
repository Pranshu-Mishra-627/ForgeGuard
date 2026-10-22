"use client";
import React from "react";
import { Machine } from "@/lib/types";
import { TechnicianAllocation } from "../overview/TechnicianAllocation";
import { MachineRiskTable } from "../overview/MachineRiskTable";
import { Wrench, ShieldCheck, AlertCircle } from "lucide-react";
import { formatCurrency } from "@/lib/data-generator";

interface PlannerViewProps {
  machines: Machine[];
  slots: number;
  onSlotsChange: (slots: number) => void;
  threshold: number;
  scheduledMachines: Machine[];
  deferredMachines: Machine[];
  reasonsById: Map<string, string>;
  statusById: Map<string, "scheduled" | "deferred">;
  unmitigatedExposure: number;
  avoidedExposure: number;
  onSelectMachine: (m: Machine) => void;
}

export const PlannerView: React.FC<PlannerViewProps> = ({
  machines,
  slots,
  onSlotsChange,
  threshold,
  scheduledMachines,
  deferredMachines,
  reasonsById,
  statusById,
  unmitigatedExposure,
  avoidedExposure,
  onSelectMachine,
}) => {
  return (
    <div className="space-y-6">
      {/* Shift Overview Banner */}
      <div className="panel p-5 sm:p-6 bg-surface grid grid-cols-1 gap-4 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-border-subtle border border-border-normal">
        <div className="flex items-center gap-4 sm:px-4">
          <Wrench className="size-6 text-accent-forest shrink-0" />
          <div>
            <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
              Technician Capacity
            </span>
            <span className="font-mono text-xl sm:text-2xl font-bold text-foreground">
              {scheduledMachines.length} of {slots} slots utilized
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4 sm:px-6">
          <ShieldCheck className="size-6 text-accent-forest shrink-0" />
          <div>
            <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
              Mitigated Catastrophic Risk
            </span>
            <span className="font-mono text-xl sm:text-2xl font-bold text-accent-forest">
              {formatCurrency(avoidedExposure)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4 sm:px-6">
          <AlertCircle className="size-6 text-status-warning shrink-0" />
          <div>
            <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
              Deferred Failure Exposure
            </span>
            <span className="font-mono text-xl sm:text-2xl font-bold text-status-warning">
              {deferredMachines.length > 0 ? formatCurrency(unmitigatedExposure) : "$0.0K"}
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid: Technician Allocation (5 cols) + Machine Table (7 cols) */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-5">
          <TechnicianAllocation
            slots={slots}
            onSlotsChange={onSlotsChange}
            threshold={threshold}
            scheduledMachines={scheduledMachines}
            deferredMachines={deferredMachines}
            reasonsById={reasonsById}
            unmitigatedExposure={unmitigatedExposure}
            onSelectMachine={onSelectMachine}
            listHeight="max-h-[640px]"
          />
        </div>
        <div className="xl:col-span-7">
          <MachineRiskTable
            machines={machines}
            statusById={statusById}
            onSelectMachine={onSelectMachine}
            maxHeight="max-h-[680px]"
          />
        </div>
      </div>
    </div>
  );
};
