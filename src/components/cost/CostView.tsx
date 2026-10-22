"use client";
import React from "react";
import { Machine, ThresholdCostPoint } from "@/lib/types";
import { CostAnalysisChart } from "../overview/CostAnalysisChart";
import { RiskDistributionChart } from "../overview/RiskDistributionChart";
import { formatCurrency } from "@/lib/data-generator";

interface CostViewProps {
  machines: Machine[];
  slots: number;
  costCurve: ThresholdCostPoint[];
  selectedThreshold: number;
  onThresholdChange: (t: number) => void;
  optimalPoint: ThresholdCostPoint;
  scheduledMachines: Machine[];
  deferredMachines: Machine[];
  inspectionCost?: number;
  alertReviewCost?: number;
  onSelectMachine: (m: Machine) => void;
}

export const CostView: React.FC<CostViewProps> = ({
  machines,
  slots,
  costCurve,
  selectedThreshold,
  onThresholdChange,
  optimalPoint,
  scheduledMachines,
  deferredMachines,
  inspectionCost = 1800,
  alertReviewCost = 260,
  onSelectMachine,
}) => {
  const currentPoint =
    costCurve.find((p) => Math.abs(p.threshold - selectedThreshold) < 0.001) ??
    costCurve[0];

  return (
    <div className="space-y-6">
      {/* Cost Architecture KPI Header */}
      <div className="panel p-5 sm:p-6 bg-surface grid grid-cols-1 gap-4 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border-subtle border border-border-normal">
        <div className="sm:px-4">
          <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
            Current Shift Cost
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground block mt-1.5">
            {formatCurrency(currentPoint.cost)}
          </span>
          <span className="text-xs sm:text-[13px] text-foreground-muted block mt-1">
            At {Math.round(selectedThreshold * 100)}% alert threshold
          </span>
        </div>

        <div className="sm:px-6">
          <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
            Optimal Cost Floor
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-forest block mt-1.5">
            {formatCurrency(optimalPoint.cost)}
          </span>
          <span className="text-xs sm:text-[13px] text-foreground-muted block mt-1">
            At {Math.round(optimalPoint.threshold * 100)}% threshold
          </span>
        </div>

        <div className="sm:px-6">
          <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
            Inspection Expenditure
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-terracotta block mt-1.5">
            {formatCurrency(currentPoint.maintenanceCost)}
          </span>
          <span className="text-xs sm:text-[13px] text-foreground-muted block mt-1">
            {scheduledMachines.length} dispatches · {formatCurrency(inspectionCost)}/slot
          </span>
        </div>

        <div className="sm:px-6">
          <span className="text-foreground-muted text-xs uppercase font-semibold tracking-wider block">
            Residual Failure Risk
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-status-critical block mt-1.5">
            {formatCurrency(currentPoint.failureCost)}
          </span>
          <span className="text-xs sm:text-[13px] text-foreground-muted block mt-1">
            Unmitigated & latent risk
          </span>
        </div>
      </div>

      {/* Main Grid: Cost Analysis Curve (8 cols) + Cost Parameters & Distribution (4 cols) */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <CostAnalysisChart
            slots={slots}
            costCurve={costCurve}
            selectedThreshold={selectedThreshold}
            onThresholdChange={onThresholdChange}
            optimalPoint={optimalPoint}
            chartHeight={380}
          />
        </div>

        <div className="flex flex-col gap-6 xl:col-span-4">
          {/* Decision Engine Cost Parameters Card */}
          <div className="panel p-5 sm:p-6 bg-surface space-y-4 border border-border-normal">
            <div className="flex items-center justify-between border-b border-border-subtle pb-3">
              <span className="font-bold text-foreground text-base">
                Cost Model Parameters
              </span>
              <span className="eyebrow text-xs text-foreground-muted">
                Economic Ratios
              </span>
            </div>
            <dl className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-foreground-muted">Missed Failure Penalty (FN)</dt>
                <dd className="font-mono font-bold text-status-critical">20.0× relative</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-foreground-muted">Technician Dispatch (FP)</dt>
                <dd className="font-mono font-bold text-foreground">{formatCurrency(inspectionCost)} / service</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-foreground-muted">Diagnostic Review Overhead</dt>
                <dd className="font-mono font-bold text-foreground">{formatCurrency(alertReviewCost)} / alert</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-foreground-muted">Threshold Optimization Grid</dt>
                <dd className="font-mono font-bold text-foreground">19 points (0.05–0.95)</dd>
              </div>
            </dl>
            <div className="rounded-md border border-border-normal bg-surface-subtle p-3.5 text-xs sm:text-[13px] text-foreground-muted leading-relaxed">
              When multiple candidate thresholds produce identical minimum expected costs, the engine
              picks the <strong className="text-foreground font-semibold">highest threshold</strong> to minimize
              false alarms and reduce unnecessary technician crew fatigue.
            </div>
          </div>

          {/* Risk Distribution */}
          <RiskDistributionChart
            machines={machines}
            selectedRisk="all"
            onSelectRisk={() => {}}
          />
        </div>
      </div>
    </div>
  );
};
