"use client";
import React, { useState, useMemo } from "react";
import {
  SlidersHorizontal,
  ArrowRight,
  ShieldAlert,
  Wrench,
  DollarSign,
  AlertCircle,
  HelpCircle,
  Pin,
  PinOff,
  Scale,
  RefreshCw,
} from "lucide-react";
import { Machine, ShiftPlanResult, ThresholdCostPoint } from "@/lib/types";
import { formatCurrency } from "@/lib/data-generator";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from "recharts";

interface DecisionEngineViewProps {
  machines: Machine[];
  slots: number;
  onSlotsChange: (slots: number) => void;
  threshold: number;
  onThresholdChange: (threshold: number) => void;
  shiftPlan: ShiftPlanResult;
  costCurve: ThresholdCostPoint[];
  optimalPoint: ThresholdCostPoint;
  inspectionCost: number;
  onInspectionCostChange: (cost: number) => void;
  alertReviewCost: number;
  onAlertReviewCostChange: (cost: number) => void;
  pinnedIds: string[];
  onTogglePin: (machineId: string) => void;
  onSelectMachine: (m: Machine) => void;
}

export const DecisionEngineView: React.FC<DecisionEngineViewProps> = ({
  machines,
  slots,
  onSlotsChange,
  threshold,
  onThresholdChange,
  shiftPlan,
  costCurve,
  optimalPoint,
  inspectionCost,
  onInspectionCostChange,
  alertReviewCost,
  onAlertReviewCostChange,
  pinnedIds,
  onTogglePin,
  onSelectMachine,
}) => {
  // Explainability Machine Comparison state
  const alertedMachines = shiftPlan.ranked;
  const [compareMachineAId, setCompareMachineAId] = useState<string>(
    alertedMachines[0]?.id ?? machines[0]?.id ?? ""
  );
  const [compareMachineBId, setCompareMachineBId] = useState<string>(
    alertedMachines[slots]?.id ?? alertedMachines[1]?.id ?? machines[1]?.id ?? ""
  );

  const machineA = machines.find((m) => m.id === compareMachineAId) ?? machines[0];
  const machineB = machines.find((m) => m.id === compareMachineBId) ?? machines[1];

  const machineAIndex = alertedMachines.findIndex((m) => m.id === machineA?.id);
  const isScheduledA = machineAIndex !== -1 && machineAIndex < slots;
  const machineBIndex = alertedMachines.findIndex((m) => m.id === machineB?.id);
  const isScheduledB = machineBIndex !== -1 && machineBIndex < slots;

  // Explainability comparison narrative
  const comparisonNarrative = useMemo(() => {
    if (!machineA || !machineB || machineA.id === machineB.id) {
      return "Select two distinct machines to inspect why one is prioritized over the other.";
    }

    const expA = machineA.probability * machineA.failureCost;
    const expB = machineB.probability * machineB.failureCost;
    const isAPinned = pinnedIds.includes(machineA.id);
    const isBPinned = pinnedIds.includes(machineB.id);

    if (isAPinned && !isBPinned) {
      return `${machineA.id} ranks above ${machineB.id} because it was manually prioritized by a plant supervisor override pin, granting slot priority regardless of raw score.`;
    }
    if (isBPinned && !isAPinned) {
      return `${machineB.id} ranks above ${machineA.id} due to supervisor override pin on ${machineB.id}.`;
    }

    if (machineA.priority > machineB.priority) {
      return `${machineA.id} (P${machineA.priority}) ranks above ${machineB.id} (P${machineB.priority}) because its expected loss of ${formatCurrency(expA)} (${(machineA.probability * 100).toFixed(0)}% × ${formatCurrency(machineA.failureCost)}) exceeds ${machineB.id}'s expected loss of ${formatCurrency(expB)} (${(machineB.probability * 100).toFixed(0)}% × ${formatCurrency(machineB.failureCost)}).`;
    } else if (machineB.priority > machineA.priority) {
      return `${machineB.id} (P${machineB.priority}) ranks above ${machineA.id} (P${machineA.priority}) because its expected loss of ${formatCurrency(expB)} exceeds ${machineA.id}'s expected loss of ${formatCurrency(expA)}.`;
    } else {
      return `${machineA.id} and ${machineB.id} share equal priority score (${machineA.priority}). Order is resolved by asset identifier sequence.`;
    }
  }, [machineA, machineB, pinnedIds]);

  // Formatted cost curve data for display
  const chartData = costCurve.map((p) => ({
    ...p,
    thresholdPct: `${Math.round(p.threshold * 100)}%`,
    totalCostK: Math.round(p.cost / 1000),
    failureCostK: Math.round(p.failureCost / 1000),
    maintenanceCostK: Math.round(p.maintenanceCost / 1000),
  }));

  const currentCostPoint =
    costCurve.find((p) => Math.abs(p.threshold - threshold) < 0.001) ?? costCurve[0];

  return (
    <div className="space-y-6">
      {/* 1. Core Distinction Card: 3-Stage Decision Framework */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle pb-4">
          <div className="flex items-center gap-2.5">
            <Scale className="size-5 text-accent-forest" />
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Three-Stage Maintenance Decision Framework
            </h2>
          </div>
          <span className="eyebrow text-xs text-foreground-muted">
            Telemetry Inference · Economic Assessment · Capacity Roster
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
          {/* Stage 1: Model prediction */}
          <div className="rounded-md border border-border-normal bg-surface-subtle p-4 sm:p-5 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="inline-flex items-center gap-1 rounded bg-accent-forest-subtle border border-accent-forest-border px-2 py-0.5 text-xs font-mono font-bold uppercase text-accent-forest">
                  Stage 1
                </span>
                <span className="text-xs font-mono text-foreground-muted">fg-gbm v3.2</span>
              </div>
              <h3 className="font-bold text-foreground text-sm sm:text-base">
                Model prediction
              </h3>
              <p className="text-foreground-muted leading-relaxed text-[13px] mt-1.5">
                Gradient boosted tree scores physical sensor telemetry (vibration RMS, tool wear, ΔT, torque draw) to estimate anomaly probability <span className="font-mono font-bold text-foreground">P(Failure)</span> and classify the primary failure mode.
              </p>
            </div>
            <div className="border-t border-border-subtle pt-3 flex items-center justify-between text-xs sm:text-[13px]">
              <span className="text-foreground-muted">Input Signals:</span>
              <span className="font-mono text-foreground font-semibold">6 Telemetry Feeds</span>
            </div>
          </div>

          {/* Stage 2: Cost assessment */}
          <div className="rounded-md border border-border-normal bg-surface-subtle p-4 sm:p-5 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="inline-flex items-center gap-1 rounded bg-accent-terracotta-subtle border border-accent-terracotta-border px-2 py-0.5 text-xs font-mono font-bold uppercase text-accent-terracotta">
                  Stage 2
                </span>
                <span className="text-xs font-mono text-foreground-muted">Cost Curve</span>
              </div>
              <h3 className="font-bold text-foreground text-sm sm:text-base">
                Cost assessment
              </h3>
              <p className="text-foreground-muted leading-relaxed text-[13px] mt-1.5">
                Weighs failure probability by asset downtime loss to calculate <span className="font-mono font-bold text-foreground">Expected Loss</span>. Balances dispatch cost (${inspectionCost}) and alert review overhead (${alertReviewCost}) to determine optimal threshold.
              </p>
            </div>
            <div className="border-t border-border-subtle pt-3 flex items-center justify-between text-xs sm:text-[13px]">
              <span className="text-foreground-muted">Threshold:</span>
              <span className="font-mono text-foreground font-semibold">{Math.round(threshold * 100)}% (Floor: {Math.round(optimalPoint.threshold * 100)}%)</span>
            </div>
          </div>

          {/* Stage 3: Scheduling decision */}
          <div className="rounded-md border border-border-normal bg-surface-subtle p-4 sm:p-5 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="inline-flex items-center gap-1 rounded bg-surface border border-border-strong px-2 py-0.5 text-xs font-mono font-bold uppercase text-foreground">
                  Stage 3
                </span>
                <span className="text-xs font-mono text-foreground-muted">Dispatch Queue</span>
              </div>
              <h3 className="font-bold text-foreground text-sm sm:text-base">
                Scheduling decision
              </h3>
              <p className="text-foreground-muted leading-relaxed text-[13px] mt-1.5">
                Sorts candidate machines by priority score into available technician slots (<span className="font-mono font-bold text-foreground">{slots} slots</span>). Top units are scheduled; remaining units are deferred with explicit risk justifications and override pins.
              </p>
            </div>
            <div className="border-t border-border-subtle pt-3 flex items-center justify-between text-xs sm:text-[13px]">
              <span className="text-foreground-muted">Shift Roster:</span>
              <span className="font-mono text-accent-forest font-bold">{shiftPlan.scheduled.length} Sched · {shiftPlan.deferred.length} Defer</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Interactive Decision Parameters & Sliders Dock */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle pb-4">
          <div>
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Operational Assumptions & Capacity Tuning
            </h2>
            <p className="text-[13px] text-foreground-muted mt-0.5">
              Adjust economic parameters and technician availability to see immediate updates across dispatch priority.
            </p>
          </div>

          {/* Preset Buttons */}
          <div className="flex flex-wrap gap-2" role="group" aria-label="Decision Presets">
            <button
              type="button"
              onClick={() => {
                onThresholdChange(optimalPoint.threshold);
                onSlotsChange(6);
              }}
              className="h-9 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors"
            >
              Balanced / Cost-Optimal
            </button>
            <button
              type="button"
              onClick={() => {
                onThresholdChange(0.25);
                onSlotsChange(8);
              }}
              className="h-9 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors"
            >
              Risk-Averse (Early Alerts)
            </button>
            <button
              type="button"
              onClick={() => {
                onThresholdChange(0.6);
                onSlotsChange(4);
              }}
              className="h-9 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors"
            >
              Capacity-Constrained
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 text-xs">
          {/* A. Alert Threshold Slider */}
          <div className="space-y-2.5 rounded-md border border-border-normal bg-surface-subtle p-4">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground text-[13.5px]">
                Alert Threshold
              </span>
              <span className="font-mono text-base font-bold text-accent-forest">
                {Math.round(threshold * 100)}%
              </span>
            </div>
            <input
              type="range"
              min={0.05}
              max={0.95}
              step={0.05}
              value={threshold}
              onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
              aria-label="Alert threshold slider"
              className="w-full h-2 cursor-pointer appearance-none rounded bg-surface border border-border-normal accent-accent-forest"
            />
            <p className="text-xs text-foreground-muted leading-relaxed">
              Machines below {Math.round(threshold * 100)}% will not trigger alerts or crew dispatches.
            </p>
          </div>

          {/* B. Technician Availability */}
          <div className="space-y-2.5 rounded-md border border-border-normal bg-surface-subtle p-4">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground text-[13.5px]">
                Technician Slots
              </span>
              <span className="font-mono text-base font-bold text-foreground">
                {slots} slots
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={16}
                step={1}
                value={slots}
                onChange={(e) => onSlotsChange(parseInt(e.target.value, 10))}
                aria-label="Technician slots slider"
                className="w-full h-2 cursor-pointer appearance-none rounded bg-surface border border-border-normal accent-accent-forest"
              />
            </div>
            <p className="text-xs text-foreground-muted leading-relaxed">
              Maximum maintenance work orders executable in this 8-hour shift.
            </p>
          </div>

          {/* C. Technician Dispatch Cost Input */}
          <div className="space-y-2.5 rounded-md border border-border-normal bg-surface-subtle p-4">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground text-[13.5px]">
                Dispatch Inspection Cost
              </span>
              <span className="font-mono text-base font-bold text-foreground">
                ${inspectionCost}
              </span>
            </div>
            <input
              type="range"
              min={1000}
              max={4000}
              step={100}
              value={inspectionCost}
              onChange={(e) => onInspectionCostChange(parseInt(e.target.value, 10))}
              aria-label="Dispatch inspection cost slider"
              className="w-full h-2 cursor-pointer appearance-none rounded bg-surface border border-border-normal accent-accent-forest"
            />
            <p className="text-xs text-foreground-muted leading-relaxed">
              Labor, tooling setup, and lockout-tagout cost per scheduled dispatch.
            </p>
          </div>

          {/* D. Alert Review Overhead Input */}
          <div className="space-y-2.5 rounded-md border border-border-normal bg-surface-subtle p-4">
            <div className="flex items-center justify-between">
              <span className="font-bold text-foreground text-[13.5px]">
                Alert Diagnostic Review
              </span>
              <span className="font-mono text-base font-bold text-foreground">
                ${alertReviewCost}
              </span>
            </div>
            <input
              type="range"
              min={100}
              max={600}
              step={20}
              value={alertReviewCost}
              onChange={(e) => onAlertReviewCostChange(parseInt(e.target.value, 10))}
              aria-label="Alert diagnostic review cost slider"
              className="w-full h-2 cursor-pointer appearance-none rounded bg-surface border border-border-normal accent-accent-forest"
            />
            <p className="text-xs text-foreground-muted leading-relaxed">
              Supervisor analysis overhead per triggered telemetry notification.
            </p>
          </div>
        </div>
      </div>

      {/* 3. Decision Ranking Explainability Inspector: Why Machine A ranks above Machine B */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle pb-4">
          <div>
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Ranking Explainability Inspector
            </h2>
            <p className="text-[13px] text-foreground-muted mt-0.5">
              Select two machines to evaluate the explicit economic justification behind priority ordering.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground-muted">Unit A:</span>
              <select
                aria-label="Select Machine A"
                value={compareMachineAId}
                onChange={(e) => setCompareMachineAId(e.target.value)}
                className="h-10 rounded-md border border-border-normal bg-surface px-3 text-xs sm:text-sm font-mono font-medium text-foreground focus-visible:outline-none"
              >
                {machines.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id} (P{m.priority})
                  </option>
                ))}
              </select>
            </div>

            <ArrowRight className="size-4 text-foreground-muted" />

            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground-muted">Unit B:</span>
              <select
                aria-label="Select Machine B"
                value={compareMachineBId}
                onChange={(e) => setCompareMachineBId(e.target.value)}
                className="h-10 rounded-md border border-border-normal bg-surface px-3 text-xs sm:text-sm font-mono font-medium text-foreground focus-visible:outline-none"
              >
                {machines.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id} (P{m.priority})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Comparison Result Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Card A */}
          <div
            className={`rounded-md border p-4 sm:p-5 flex flex-col justify-between space-y-3.5 ${
              (machineA?.priority ?? 0) >= (machineB?.priority ?? 0)
                ? "border-accent-forest-border bg-accent-forest-subtle"
                : "border-border-normal bg-surface-subtle"
            }`}
          >
            <div className="flex items-center justify-between border-b border-border-subtle pb-3">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-base font-bold text-foreground">
                  {machineA?.id}
                </span>
                <span className="text-xs text-foreground-muted">
                  {machineA?.type} · {machineA?.line}
                </span>
              </div>
              <span className="rounded-md px-2 py-0.5 font-mono text-xs uppercase font-bold text-accent-forest bg-surface border border-accent-forest-border">
                Score {machineA?.priority}
              </span>
            </div>

            {/* 3 Labeled Stages */}
            <div className="space-y-2.5 text-xs">
              {/* Stage 1: Model prediction */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-accent-forest mb-2">
                  <span>1. Model prediction</span>
                  <span className="font-mono font-normal text-foreground-muted">P(Fail)</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-foreground-muted text-xs block">Failure Probability</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {((machineA?.probability ?? 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-foreground-muted text-xs block">Predicted Mode</span>
                    <span className="font-medium text-foreground truncate block text-xs sm:text-sm" title={machineA?.failureMode}>
                      {machineA?.failureMode}
                    </span>
                  </div>
                </div>
              </div>

              {/* Stage 2: Cost assessment */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-accent-terracotta mb-2">
                  <span>2. Cost assessment</span>
                  <span className="font-mono font-normal text-foreground-muted">Exposure</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-foreground-muted text-xs block">Asset Downtime Loss</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {formatCurrency(machineA?.failureCost ?? 0)}
                    </span>
                  </div>
                  <div>
                    <span className="text-foreground-muted text-xs block">Expected Exposure</span>
                    <span className="font-mono font-bold text-status-critical text-sm">
                      {formatCurrency((machineA?.probability ?? 0) * (machineA?.failureCost ?? 0))}
                    </span>
                  </div>
                </div>
              </div>

              {/* Stage 3: Scheduling decision */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-foreground mb-2">
                  <span>3. Scheduling decision</span>
                  <span className="font-mono font-normal text-foreground-muted">Shift Action</span>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-foreground-muted text-xs block">Priority Ranking</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {machineAIndex !== -1 ? `#${machineAIndex + 1}` : "Below Threshold"} (Score {machineA?.priority})
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-foreground-muted text-xs block">Shift Status</span>
                    {isScheduledA ? (
                      <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-healthy bg-status-healthy-bg border border-status-healthy-border">
                        Slot #{machineAIndex + 1} Scheduled
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-warning bg-status-warning-bg border border-status-warning-border">
                        Deferred (Capacity)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Card B */}
          <div
            className={`rounded-md border p-4 sm:p-5 flex flex-col justify-between space-y-3.5 ${
              (machineB?.priority ?? 0) > (machineA?.priority ?? 0)
                ? "border-accent-forest-border bg-accent-forest-subtle"
                : "border-border-normal bg-surface-subtle"
            }`}
          >
            <div className="flex items-center justify-between border-b border-border-subtle pb-3">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-base font-bold text-foreground">
                  {machineB?.id}
                </span>
                <span className="text-xs text-foreground-muted">
                  {machineB?.type} · {machineB?.line}
                </span>
              </div>
              <span className="rounded-md px-2 py-0.5 font-mono text-xs uppercase font-bold text-accent-forest bg-surface border border-accent-forest-border">
                Score {machineB?.priority}
              </span>
            </div>

            {/* 3 Labeled Stages */}
            <div className="space-y-2.5 text-xs">
              {/* Stage 1: Model prediction */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-accent-forest mb-2">
                  <span>1. Model prediction</span>
                  <span className="font-mono font-normal text-foreground-muted">P(Fail)</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-foreground-muted text-xs block">Failure Probability</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {((machineB?.probability ?? 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-foreground-muted text-xs block">Predicted Mode</span>
                    <span className="font-medium text-foreground truncate block text-xs sm:text-sm" title={machineB?.failureMode}>
                      {machineB?.failureMode}
                    </span>
                  </div>
                </div>
              </div>

              {/* Stage 2: Cost assessment */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-accent-terracotta mb-2">
                  <span>2. Cost assessment</span>
                  <span className="font-mono font-normal text-foreground-muted">Exposure</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-foreground-muted text-xs block">Asset Downtime Loss</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {formatCurrency(machineB?.failureCost ?? 0)}
                    </span>
                  </div>
                  <div>
                    <span className="text-foreground-muted text-xs block">Expected Exposure</span>
                    <span className="font-mono font-bold text-status-critical text-sm">
                      {formatCurrency((machineB?.probability ?? 0) * (machineB?.failureCost ?? 0))}
                    </span>
                  </div>
                </div>
              </div>

              {/* Stage 3: Scheduling decision */}
              <div className="rounded-md bg-surface p-3 border border-border-subtle">
                <div className="flex items-center justify-between text-xs uppercase tracking-wider font-bold text-foreground mb-2">
                  <span>3. Scheduling decision</span>
                  <span className="font-mono font-normal text-foreground-muted">Shift Action</span>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-foreground-muted text-xs block">Priority Ranking</span>
                    <span className="font-mono font-bold text-foreground text-sm">
                      {machineBIndex !== -1 ? `#${machineBIndex + 1}` : "Below Threshold"} (Score {machineB?.priority})
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-foreground-muted text-xs block">Shift Status</span>
                    {isScheduledB ? (
                      <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-healthy bg-status-healthy-bg border border-status-healthy-border">
                        Slot #{machineBIndex + 1} Scheduled
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-warning bg-status-warning-bg border border-status-warning-border">
                        Deferred (Capacity)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Narrative Box */}
        <div className="rounded-md border border-border-normal bg-surface-subtle p-4 text-[13.5px] text-foreground leading-relaxed">
          <span className="font-bold text-accent-forest mr-1.5">Engine Conclusion:</span>
          {comparisonNarrative}
        </div>
      </div>

      {/* 4. Complete Shift Decision Manifest Table */}
      <div className="panel flex flex-col overflow-hidden bg-surface border border-border-normal">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-normal px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Shift Decision Manifest
            </h2>
            <p className="mt-0.5 text-[13px] text-foreground-muted">
              Capacity: {shiftPlan.scheduled.length} scheduled work orders · {shiftPlan.deferred.length} deferred units
            </p>
          </div>
        </div>

        <div className="overflow-auto max-h-[520px]">
          <table className="w-full min-w-[1040px] border-collapse text-left text-sm">
            <thead className="sticky top-0 z-10 bg-surface-subtle border-b border-border-normal">
              {/* Category Grouping Row */}
              <tr className="border-b border-border-subtle text-xs font-mono uppercase tracking-wider text-foreground-muted select-none">
                <th colSpan={2} className="pl-4 pr-2 py-2 font-bold text-foreground/80">
                  Asset
                </th>
                <th colSpan={2} className="px-4 py-2 font-bold text-accent-forest border-l border-border-subtle">
                  1. Model prediction
                </th>
                <th colSpan={2} className="px-4 py-2 font-bold text-accent-terracotta border-l border-border-subtle">
                  2. Cost assessment
                </th>
                <th colSpan={4} className="px-4 pr-4 py-2 font-bold text-foreground border-l border-border-subtle">
                  3. Scheduling decision
                </th>
              </tr>
              <tr className="eyebrow h-11 text-foreground-muted select-none">
                <th scope="col" className="pl-4 pr-2 font-bold w-14">
                  Rank
                </th>
                <th scope="col" className="px-4 font-bold">
                  Machine ID & Line
                </th>
                <th scope="col" className="px-4 font-bold border-l border-border-subtle">
                  Probability
                </th>
                <th scope="col" className="px-4 font-bold">
                  Predicted Failure Mode
                </th>
                <th scope="col" className="px-4 font-bold border-l border-border-subtle text-right">
                  Downtime Loss
                </th>
                <th scope="col" className="px-4 font-bold text-right">
                  Expected Loss
                </th>
                <th scope="col" className="px-4 font-bold border-l border-border-subtle">
                  Score
                </th>
                <th scope="col" className="px-4 font-bold">
                  Decision & Slot
                </th>
                <th scope="col" className="px-4 font-bold">
                  Engine Rationale
                </th>
                <th scope="col" className="pr-4 pl-2 text-right font-bold">
                  Pin Override
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle bg-surface">
              {shiftPlan.ranked.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-sm text-foreground-muted">
                    No machines at or above the {Math.round(threshold * 100)}% threshold.
                  </td>
                </tr>
              ) : (
                shiftPlan.ranked.map((m, idx) => {
                  const isScheduled = idx < slots;
                  const isPinned = pinnedIds.includes(m.id);
                  const reason = shiftPlan.reasonsById.get(m.id) ?? "";
                  const expectedLoss = m.probability * m.failureCost;

                  return (
                    <tr
                      key={m.id}
                      className="group cursor-pointer hover:bg-surface-hover transition-colors"
                      onClick={() => onSelectMachine(m)}
                    >
                      {/* Rank */}
                      <td className="py-3.5 pl-4 pr-2 font-mono text-xs font-bold text-foreground-muted">
                        #{idx + 1}
                      </td>

                      {/* Machine ID */}
                      <td className="px-4 py-3.5">
                        <span className="font-mono text-[14px] font-bold text-foreground block">
                          {m.id}
                        </span>
                        <span className="text-xs text-foreground-muted block mt-0.5">
                          {m.type} · {m.line}
                        </span>
                      </td>

                      {/* Probability (Model prediction) */}
                      <td className="px-4 py-3.5 font-mono text-sm font-bold tabular-nums border-l border-border-subtle">
                        <span
                          className={
                            m.risk === "critical"
                              ? "text-status-critical"
                              : m.risk === "high"
                              ? "text-status-warning"
                              : "text-accent-forest"
                          }
                        >
                          {(m.probability * 100).toFixed(1)}%
                        </span>
                      </td>

                      {/* Failure Mode (Model prediction) */}
                      <td className="px-4 py-3.5 text-foreground font-medium text-[13.5px] whitespace-nowrap">
                        {m.failureMode}
                      </td>

                      {/* Downtime Loss (Cost assessment) */}
                      <td className="px-4 py-3.5 font-mono text-sm text-foreground tabular-nums text-right border-l border-border-subtle">
                        {formatCurrency(m.failureCost)}
                      </td>

                      {/* Expected Loss (Cost assessment) */}
                      <td className="px-4 py-3.5 font-mono text-sm font-bold text-status-critical tabular-nums text-right">
                        {formatCurrency(expectedLoss)}
                      </td>

                      {/* Priority (Scheduling decision) */}
                      <td className="px-4 py-3.5 font-mono text-sm font-bold text-foreground border-l border-border-subtle">
                        {m.priority}
                      </td>

                      {/* Decision & Slot */}
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        {isScheduled ? (
                          <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-healthy bg-status-healthy-bg border border-status-healthy-border">
                            Slot #{idx + 1} Sched
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded px-2 py-0.5 font-mono text-xs font-bold uppercase text-status-warning bg-status-warning-bg border border-status-warning-border">
                            Deferred (Capacity)
                          </span>
                        )}
                      </td>

                      {/* Rationale */}
                      <td className="px-4 py-3.5 max-w-xs xl:max-w-md text-foreground-muted text-[13px] leading-relaxed">
                        <p className="truncate group-hover:text-foreground" title={reason}>
                          {reason}
                        </p>
                      </td>

                      {/* Pin Toggle */}
                      <td className="pr-4 pl-2 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => onTogglePin(m.id)}
                          className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
                            isPinned
                              ? "bg-accent-terracotta-subtle text-accent-terracotta border-accent-terracotta-border"
                              : "bg-surface text-foreground-muted border-border-normal hover:bg-surface-hover hover:text-foreground"
                          }`}
                          title={isPinned ? "Remove manual override pin" : "Pin machine to slot #1"}
                        >
                          {isPinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                          <span>{isPinned ? "Pinned" : "Pin"}</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
