"use client";
import React, { useEffect } from "react";
import {
  X,
  Pin,
  PinOff,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Machine } from "@/lib/types";

interface MachineDetailDrawerProps {
  machine: Machine | null;
  isOpen: boolean;
  onClose: () => void;
  status?: "scheduled" | "deferred";
  isPinned: boolean;
  onTogglePin: (machineId: string) => void;
}

export const MachineDetailDrawer: React.FC<MachineDetailDrawerProps> = ({
  machine,
  isOpen,
  onClose,
  status,
  isPinned,
  onTogglePin,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !machine) return null;

  const t = machine.telemetry;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/25 backdrop-blur-[2px]">
      {/* Backdrop click to close */}
      <div className="absolute inset-0" onClick={onClose} aria-hidden="true" />

      {/* Drawer Panel */}
      <aside
        className="relative z-10 flex h-full w-full max-w-lg flex-col border-l border-border-normal bg-background shadow-xl overflow-hidden"
        role="dialog"
        aria-label={`Details for ${machine.id}`}
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-normal bg-surface px-6 py-4.5">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-xl font-bold text-foreground">
                  {machine.id}
                </span>
                {status === "scheduled" && (
                  <span className="rounded-md px-2.5 py-0.5 font-mono text-xs uppercase text-status-healthy bg-status-healthy-bg border border-status-healthy-border font-bold">
                    Scheduled
                  </span>
                )}
                {status === "deferred" && (
                  <span className="rounded-md px-2.5 py-0.5 font-mono text-xs uppercase text-status-warning bg-status-warning-bg border border-status-warning-border font-bold">
                    Deferred
                  </span>
                )}
                {isPinned && (
                  <span className="rounded-md px-2.5 py-0.5 font-mono text-xs uppercase text-accent-terracotta bg-accent-terracotta-subtle border border-accent-terracotta-border font-bold">
                    Pinned Override
                  </span>
                )}
              </div>
              <p className="text-[13px] text-foreground-muted mt-1">
                {machine.type} · {machine.line}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Pin Toggle Button */}
            <button
              type="button"
              onClick={() => onTogglePin(machine.id)}
              className={`inline-flex h-9 items-center gap-2 rounded-md border px-3.5 text-xs font-semibold transition-colors focus-visible:outline-none ${
                isPinned
                  ? "bg-accent-terracotta-subtle text-accent-terracotta border-accent-terracotta-border hover:bg-accent-terracotta-subtle/80"
                  : "bg-surface text-foreground-muted border-border-normal hover:bg-surface-hover hover:text-foreground"
              }`}
            >
              {isPinned ? (
                <>
                  <PinOff className="size-4" />
                  <span>Unpin</span>
                </>
              ) : (
                <>
                  <Pin className="size-4" />
                  <span>Pin to Shift</span>
                </>
              )}
            </button>

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              className="flex size-9 items-center justify-center rounded-md border border-border-normal bg-surface text-foreground-muted hover:bg-surface-hover hover:text-foreground focus-visible:outline-none"
              aria-label="Close drawer"
            >
              <X className="size-4.5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Action Recommendation Banner */}
          <div className="panel p-5 space-y-2 border-l-4 border-l-accent-forest bg-surface border border-border-normal rounded-md">
            <div className="flex items-center justify-between text-sm font-bold">
              <span className="text-foreground">Recommended Maintenance Action</span>
              <span className="font-mono text-status-critical">
                {(machine.probability * 100).toFixed(1)}% Failure Prob.
              </span>
            </div>
            <p className="text-[13.5px] text-foreground leading-relaxed">
              {machine.recommendation}
            </p>
            <p className="text-xs text-foreground-muted pt-1 border-t border-border-subtle">
              Diagnostic Root Cause: {machine.reason}
            </p>
          </div>

          {/* Condition Telemetry Grid */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="eyebrow text-foreground-muted text-xs">
                Condition Telemetry
              </h3>
              <span className="text-xs text-foreground-muted font-mono">
                Real-time multi-sensor snapshot
              </span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Air Temp</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.airTemp} K
                </span>
              </div>
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Process Temp</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.processTemp} K
                </span>
              </div>
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Spindle Speed</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.rpm} RPM
                </span>
              </div>
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Torque</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.torque} Nm
                </span>
              </div>
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Tool Wear</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.toolWear} min
                </span>
              </div>
              <div className="panel p-3.5 bg-surface border border-border-normal rounded-md">
                <span className="text-foreground-muted text-xs uppercase font-semibold block">Vibration RMS</span>
                <span className="font-mono text-base font-bold text-foreground mt-1 block">
                  {t.vibration} mm/s
                </span>
              </div>
            </div>
          </div>

          {/* 24-Hour Failure Probability Trend */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="eyebrow text-foreground-muted text-xs">
                24h Risk Trajectory
              </h3>
              <span className="text-xs font-mono text-foreground-muted">
                Hourly inference
              </span>
            </div>
            <div className="panel p-4 bg-surface border border-border-normal rounded-md">
              <div className="h-44 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={machine.trend}
                    margin={{ top: 10, right: 12, left: -14, bottom: 0 }}
                  >
                    <CartesianGrid strokeDasharray="2 2" stroke="#E5E2DC" vertical={false} />
                    <XAxis
                      dataKey="hour"
                      stroke="#74766F"
                      fontSize={12}
                      tickLine={false}
                      axisLine={{ stroke: "#E5E2DC" }}
                      interval={3}
                    />
                    <YAxis
                      stroke="#74766F"
                      fontSize={12}
                      tickLine={false}
                      axisLine={false}
                      domain={[0, 1]}
                      tickFormatter={(v) => `${Math.round(v * 100)}%`}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const val = payload[0].value as number;
                          return (
                            <div className="rounded-md border border-border-normal bg-surface px-3 py-1.5 text-xs font-semibold shadow-sm">
                              <span className="font-mono text-foreground">
                                {(val * 100).toFixed(1)}% P(Fail)
                              </span>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="probability"
                      stroke="#536B56"
                      strokeWidth={2.2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Feature Attribution (SHAP Contributions) */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="eyebrow text-foreground-muted text-xs">
                Model Feature Attribution
              </h3>
              <span className="text-xs text-foreground-muted">
                SHAP anomaly drivers
              </span>
            </div>
            <div className="panel divide-y divide-border-subtle bg-surface border border-border-normal rounded-md">
              {machine.features.map((f, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between px-4 py-3 text-xs sm:text-[13px]"
                >
                  <div>
                    <span className="text-foreground font-bold block">
                      {f.feature}
                    </span>
                    <span className="text-xs text-foreground-muted font-mono mt-0.5 block">
                      {f.value}
                    </span>
                  </div>
                  <div className="text-right font-mono tabular-nums">
                    <span
                      className={`text-sm font-bold ${
                        f.impact > 0
                          ? "text-status-critical"
                          : "text-accent-forest"
                      }`}
                    >
                      {f.impact > 0 ? `+${f.impact}` : f.impact}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Service History */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h3 className="eyebrow text-foreground-muted text-xs">
                Maintenance History
              </h3>
              <span className="text-xs text-foreground-muted">
                Prior work orders
              </span>
            </div>
            <div className="panel divide-y divide-border-subtle bg-surface border border-border-normal rounded-md">
              {machine.history.map((h, idx) => (
                <div key={idx} className="px-4 py-3 text-xs sm:text-[13px]">
                  <div className="flex items-center justify-between text-foreground">
                    <span className="font-bold">{h.action}</span>
                    <span className="font-mono text-xs text-foreground-muted">
                      {h.date}
                    </span>
                  </div>
                  <p className="text-xs text-foreground-muted mt-1">
                    Lead Technician: {h.technician}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
};
