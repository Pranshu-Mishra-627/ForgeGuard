"use client";
import React, { useState } from "react";
import {
  Settings,
  Download,
  RotateCcw,
  CheckCircle2,
  Sliders,
  DollarSign,
  Shield,
  Clock,
  FileSpreadsheet,
} from "lucide-react";
import { Machine, ShiftPlanResult } from "@/lib/types";
import { PLANTS, SHIFTS } from "@/lib/data-generator";

interface SettingsViewProps {
  slots: number;
  onSlotsChange: (slots: number) => void;
  threshold: number;
  onThresholdChange: (threshold: number) => void;
  inspectionCost: number;
  onInspectionCostChange: (cost: number) => void;
  alertReviewCost: number;
  onAlertReviewCostChange: (cost: number) => void;
  selectedPlant: string;
  selectedShift: string;
  shiftPlan: ShiftPlanResult;
  onTriggerToast: (msg: string) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  slots,
  onSlotsChange,
  threshold,
  onThresholdChange,
  inspectionCost,
  onInspectionCostChange,
  alertReviewCost,
  onAlertReviewCostChange,
  selectedPlant,
  selectedShift,
  shiftPlan,
  onTriggerToast,
}) => {
  const [technicianHourlyRate, setTechnicianHourlyRate] = useState(85);
  const [downtimeMultiplier, setDowntimeMultiplier] = useState(20);
  const [telemetryFrequency, setTelemetryFrequency] = useState("10s");

  const currentPlant = PLANTS.find((p) => p.value === selectedPlant) ?? PLANTS[0];
  const currentShift = SHIFTS.find((s) => s.value === selectedShift) ?? SHIFTS[0];

  // Export Manifest
  const handleExportManifest = () => {
    const manifest = {
      timestamp: new Date().toISOString(),
      plant: currentPlant.label,
      shift: currentShift.label,
      alertThreshold: threshold,
      technicianCapacity: slots,
      scheduledMachines: shiftPlan.scheduled.map((m, idx) => ({
        slot: idx + 1,
        machineId: m.id,
        equipmentType: m.type,
        line: m.line,
        probability: `${(m.probability * 100).toFixed(1)}%`,
        failureMode: m.failureMode,
        recommendation: m.recommendation,
        estimatedDowntimeLoss: m.failureCost,
      })),
      deferredMachines: shiftPlan.deferred.map((m) => ({
        machineId: m.id,
        probability: `${(m.probability * 100).toFixed(1)}%`,
        failureMode: m.failureMode,
      })),
    };

    const blob = new Blob([JSON.stringify(manifest, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forgeguard-workorders-${selectedPlant}-shift${selectedShift}.json`;
    a.click();
    URL.revokeObjectURL(url);

    onTriggerToast("Work order manifest exported as JSON.");
  };

  const handleResetDefaults = () => {
    onSlotsChange(6);
    onThresholdChange(0.45);
    onInspectionCostChange(1800);
    onAlertReviewCostChange(260);
    setTechnicianHourlyRate(85);
    setDowntimeMultiplier(20);
    onTriggerToast("Parameters restored to default factory baseline.");
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* 1. Header Card */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle pb-4">
          <div>
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Operational Policies & Calibration
            </h2>
            <p className="text-[13px] text-foreground-muted mt-0.5">
              Configure baseline constraints, cost assumptions, and shift parameters.
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              onClick={handleExportManifest}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors"
            >
              <Download className="size-4 text-accent-forest" />
              <span>Export Shift Work Orders (JSON)</span>
            </button>

            <button
              type="button"
              onClick={handleResetDefaults}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors"
            >
              <RotateCcw className="size-3.5" />
              <span>Reset Defaults</span>
            </button>
          </div>
        </div>

        {/* Plant Metadata Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 text-xs">
          <div className="rounded-md border border-border-normal bg-surface-subtle p-3.5 sm:p-4">
            <span className="text-xs uppercase font-semibold text-foreground-muted block">Active Facility</span>
            <span className="font-bold text-foreground text-sm sm:text-base mt-1 block">{currentPlant.label}</span>
            <span className="text-xs text-foreground-muted mt-0.5 block">{currentPlant.lines.length} production lines</span>
          </div>

          <div className="rounded-md border border-border-normal bg-surface-subtle p-3.5 sm:p-4">
            <span className="text-xs uppercase font-semibold text-foreground-muted block">Shift Envelope</span>
            <span className="font-bold text-foreground text-sm sm:text-base mt-1 block">{currentShift.label}</span>
            <span className="text-xs text-foreground-muted mt-0.5 block">8 operating hours</span>
          </div>

          <div className="rounded-md border border-border-normal bg-surface-subtle p-3.5 sm:p-4">
            <span className="text-xs uppercase font-semibold text-foreground-muted block">Model Pipeline</span>
            <span className="font-bold text-foreground text-sm sm:text-base mt-1 block font-mono">fg-gbm v3.2</span>
            <span className="text-xs text-accent-forest font-semibold mt-0.5 block">Synced · Latency 14ms</span>
          </div>
        </div>
      </div>

      {/* 2. Economic Cost Assumptions Grid */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-5">
        <h3 className="text-base font-bold text-foreground tracking-tight border-b border-border-subtle pb-3">
          Economic Cost Matrix
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 text-xs">
          <div className="space-y-2">
            <label className="font-bold text-foreground text-[13.5px] block">
              Inspection Dispatch Flat Fee ($)
            </label>
            <input
              type="number"
              value={inspectionCost}
              onChange={(e) => onInspectionCostChange(Number(e.target.value))}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 font-mono text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            />
            <span className="text-xs text-foreground-muted block">
              Direct cost of tools, PPE, and lockout procedure per slot.
            </span>
          </div>

          <div className="space-y-2">
            <label className="font-bold text-foreground text-[13.5px] block">
              Alert Diagnostic Review ($)
            </label>
            <input
              type="number"
              value={alertReviewCost}
              onChange={(e) => onAlertReviewCostChange(Number(e.target.value))}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 font-mono text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            />
            <span className="text-xs text-foreground-muted block">
              Engineer review fee per machine triggered above threshold.
            </span>
          </div>

          <div className="space-y-2">
            <label className="font-bold text-foreground text-[13.5px] block">
              Technician Loaded Hourly Rate ($/hr)
            </label>
            <input
              type="number"
              value={technicianHourlyRate}
              onChange={(e) => setTechnicianHourlyRate(Number(e.target.value))}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 font-mono text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            />
            <span className="text-xs text-foreground-muted block">
              Base labor cost including benefits and plant burden.
            </span>
          </div>
        </div>
      </div>

      {/* 3. Shift Policy & Capacity */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-5">
        <h3 className="text-base font-bold text-foreground tracking-tight border-b border-border-subtle pb-3">
          Shift Capacity Rules
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 text-xs">
          <div className="space-y-2">
            <label className="font-bold text-foreground text-[13.5px] block">
              Default Shift Technician Capacity
            </label>
            <input
              type="number"
              min={1}
              max={16}
              value={slots}
              onChange={(e) => onSlotsChange(Number(e.target.value))}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 font-mono text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            />
            <span className="text-xs text-foreground-muted block">
              Number of concurrent service windows available per 8-hour shift.
            </span>
          </div>

          <div className="space-y-2">
            <label className="font-bold text-foreground text-[13.5px] block">
              Telemetry Sample Ingestion Rate
            </label>
            <select
              aria-label="Telemetry Ingestion Rate"
              value={telemetryFrequency}
              onChange={(e) => setTelemetryFrequency(e.target.value)}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            >
              <option value="1s">1 second (High Resolution)</option>
              <option value="5s">5 seconds (Standard)</option>
              <option value="10s">10 seconds (Bandwidth-Optimized)</option>
              <option value="30s">30 seconds (Aggregate)</option>
            </select>
            <span className="text-xs text-foreground-muted block">
              IoT edge gateway streaming frequency across factory floor.
            </span>
          </div>
        </div>
      </div>

      {/* 4. Truthful Disclosure */}
      <div className="rounded-md border border-border-normal bg-surface-subtle p-4 text-xs sm:text-[13px] text-foreground-muted leading-relaxed">
        <div className="flex items-center gap-2 mb-1.5">
          <Shield className="size-4 text-accent-forest" />
          <span className="font-bold text-foreground">Operational Prototype Note</span>
        </div>
        ForgeGuard uses calibrated synthetic plant telemetry and simulated cost models for validation and demo purposes. All parameters update the in-memory decision engine calculations in real-time.
      </div>
    </div>
  );
};
