"use client";
import React, { useMemo } from "react";
import { Machine, RiskLevel } from "@/lib/types";
import { RiskDistributionChart } from "../overview/RiskDistributionChart";
import { MachineRiskTable } from "../overview/MachineRiskTable";
import { Factory } from "lucide-react";

interface FleetViewProps {
  machines: Machine[];
  statusById: Map<string, "scheduled" | "deferred">;
  onSelectMachine: (m: Machine) => void;
  selectedRisk: RiskLevel | "all";
  onSelectRisk: (risk: RiskLevel | "all") => void;
  lines: string[];
}

export const FleetView: React.FC<FleetViewProps> = ({
  machines,
  statusById,
  onSelectMachine,
  selectedRisk,
  onSelectRisk,
  lines,
}) => {
  // Line-by-line health breakdown
  const lineStats = useMemo(() => {
    return lines.map((line) => {
      const lineMachines = machines.filter((m) => m.line === line);
      const criticalCount = lineMachines.filter((m) => m.risk === "critical").length;
      const highCount = lineMachines.filter((m) => m.risk === "high").length;
      const atRiskCount = criticalCount + highCount;
      const avgProb =
        lineMachines.reduce((sum, m) => sum + m.probability, 0) /
        (lineMachines.length || 1);

      return {
        line,
        total: lineMachines.length,
        criticalCount,
        highCount,
        atRiskCount,
        avgProb: Math.round(avgProb * 100),
      };
    });
  }, [machines, lines]);

  return (
    <div className="space-y-6">
      {/* Production Line Summary Strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {lineStats.map((stat) => (
          <div
            key={stat.line}
            className="panel p-5 sm:p-6 bg-surface flex flex-col justify-between border border-border-normal"
          >
            <div className="flex items-center justify-between text-sm text-foreground-muted">
              <span className="font-bold text-foreground text-sm sm:text-base truncate">{stat.line}</span>
              <Factory className="size-4 text-foreground-muted shrink-0" />
            </div>
            <div className="mt-3.5 flex items-baseline justify-between">
              <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground">
                {stat.total} <span className="text-xs font-normal text-foreground-muted">units</span>
              </span>
              <span
                className={`font-mono text-xs sm:text-sm font-bold ${
                  stat.criticalCount > 0
                    ? "text-status-critical"
                    : stat.highCount > 0
                    ? "text-status-warning"
                    : "text-accent-forest"
                }`}
              >
                {stat.atRiskCount} at risk
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-foreground-muted border-t border-border-subtle pt-2.5">
              <span>Avg. failure probability</span>
              <span className="font-mono font-bold text-foreground">{stat.avgProb}%</span>
            </div>
          </div>
        ))}
      </div>

      {/* Main Grid: Risk Distribution + Machine Table */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-4">
          <RiskDistributionChart
            machines={machines}
            selectedRisk={selectedRisk}
            onSelectRisk={onSelectRisk}
          />
        </div>
        <div className="xl:col-span-8">
          <MachineRiskTable
            machines={machines}
            statusById={statusById}
            onSelectMachine={onSelectMachine}
            maxHeight="max-h-[680px]"
            filterRisk={selectedRisk}
            onRiskFilterChange={onSelectRisk}
            lines={lines}
          />
        </div>
      </div>
    </div>
  );
};
