"use client";
import React, { useState } from "react";
import { X, Zap, AlertTriangle, ShieldAlert, CheckCircle2 } from "lucide-react";
import { MachineContract } from "@/types/api";

interface InjectFailureModalProps {
  isOpen: boolean;
  onClose: () => void;
  machines: MachineContract[];
  onInject: (machineId: string, scenario: string) => Promise<void>;
}

export const InjectFailureModal: React.FC<InjectFailureModalProps> = ({
  isOpen,
  onClose,
  machines,
  onInject,
}) => {
  const [selectedMachineId, setSelectedMachineId] = useState(machines[0]?.machine_id ?? "M-03");
  const [scenario, setScenario] = useState("bearing_seizure");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const selectedMachine = machines.find((m) => m.machine_id === selectedMachineId) ?? machines[0];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onInject(selectedMachineId, scenario);
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 backdrop-blur-[2px] p-4">
      <div
        className="w-full max-w-lg rounded-lg border border-border-strong bg-surface p-6 shadow-2xl transition-all select-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby="failure-modal-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-subtle pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-md bg-status-critical-bg text-status-critical border border-status-critical-border">
              <Zap className="size-5 fill-current" />
            </div>
            <div>
              <h2 id="failure-modal-title" className="text-lg font-bold text-foreground">
                Demo Scenario: Inject Machine Failure
              </h2>
              <p className="text-xs text-foreground-muted mt-0.5">
                Simulate an urgent telemetry anomaly to test the decision engine & pre-emption flow.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-foreground-muted hover:bg-surface-hover hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {/* Machine Selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-foreground uppercase tracking-wider block">
              Target Asset
            </label>
            <select
              value={selectedMachineId}
              onChange={(e) => setSelectedMachineId(e.target.value)}
              className="h-10 w-full rounded-md border border-border-normal bg-surface px-3 text-sm font-mono text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            >
              {machines.map((m) => (
                <option key={m.machine_id} value={m.machine_id}>
                  {m.machine_id} — {m.name} ({m.line})
                </option>
              ))}
            </select>
          </div>

          {/* Scenario Selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-foreground uppercase tracking-wider block">
              Anomaly Failure Pattern
            </label>
            <div className="space-y-2">
              {[
                {
                  id: "bearing_seizure",
                  title: "Catastrophic Spindle Bearing Seizure",
                  desc: "Vibration RMS surges past 5.8 mm/s with thermal runaway on outer bearing race.",
                  safeToInterrupt: true,
                },
                {
                  id: "hydraulic_drop",
                  title: "Hydraulic Line Pressure Loss & Cavitation",
                  desc: "Pressure drop in primary circuit. Accumulator pressurized; triggers unsafe lockout.",
                  safeToInterrupt: false,
                },
                {
                  id: "critical_failure",
                  title: "Severe Mechanical Drive Imbalance",
                  desc: "Torque ripple spike and acoustic harmonic distortion indicating imminent shaft coupling failure.",
                  safeToInterrupt: true,
                },
              ].map((sc) => (
                <label
                  key={sc.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
                    scenario === sc.id
                      ? "border-accent-forest-border bg-accent-forest-subtle"
                      : "border-border-normal bg-surface hover:bg-surface-hover"
                  }`}
                >
                  <input
                    type="radio"
                    name="scenario"
                    value={sc.id}
                    checked={scenario === sc.id}
                    onChange={(e) => setScenario(e.target.value)}
                    className="mt-1 size-4 accent-accent-forest"
                  />
                  <div className="text-xs">
                    <span className="font-bold text-foreground block text-[13px]">
                      {sc.title}
                    </span>
                    <span className="text-foreground-muted mt-0.5 block leading-relaxed">
                      {sc.desc}
                    </span>
                    <span className="mt-1 inline-flex items-center gap-1 font-mono text-[11px] font-semibold text-foreground-muted">
                      Safety Classification:{" "}
                      <span className={sc.safeToInterrupt ? "text-accent-forest" : "text-status-critical"}>
                        {sc.safeToInterrupt ? "Safe to Tag Out" : "Lockout Required (Unsafe to Interrupt)"}
                      </span>
                    </span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Impact preview */}
          <div className="rounded-md border border-border-normal bg-surface-subtle p-3.5 text-xs text-foreground-muted">
            <div className="flex items-center gap-2 font-bold text-foreground mb-1">
              <AlertTriangle className="size-4 text-status-warning" />
              <span>Simulated Consequence</span>
            </div>
            Injecting this scenario will immediately escalate {selectedMachine?.machine_id} to 94% failure probability, trigger a critical alert banner, queue an emergency corrective work order, and open the pre-emption evaluation gate.
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-border-subtle">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-md border border-border-normal bg-surface px-4 text-xs font-semibold text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-status-critical-border bg-status-critical px-5 text-xs font-bold text-white hover:bg-status-critical/90 transition-colors shadow-sm disabled:opacity-50"
            >
              <Zap className="size-4 fill-current" />
              <span>{isSubmitting ? "Injecting..." : "Inject Scenario Now"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
