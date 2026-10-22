"use client";
import React, { useState } from "react";
import {
  Play,
  Pause,
  SkipForward,
  RotateCcw,
  Zap,
  Clock,
  Radio,
  Sliders,
  CheckCircle2,
} from "lucide-react";
import { SimulationState } from "@/types/api";

interface SimulationControlBarProps {
  state: SimulationState;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStep: (steps: number) => void;
  onReset: () => void;
  onOpenFailureModal: () => void;
  isLoading?: boolean;
}

export const SimulationControlBar: React.FC<SimulationControlBarProps> = ({
  state,
  onStart,
  onPause,
  onResume,
  onStep,
  onReset,
  onOpenFailureModal,
  isLoading = false,
}) => {
  const isRunning = state.status === "running";
  const [speed, setSpeed] = useState(state.speed || 1);

  // Format simulated timestamp
  const dateObj = new Date(state.simulated_at);
  const formattedTime = dateObj.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-normal bg-[#FAF9F5] px-5 py-2.5 text-xs text-foreground select-none">
      {/* Left: Mode badge & Disclaimer */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface px-2.5 py-1 text-[11px] font-semibold text-foreground shadow-sm">
          <span
            className={`size-2 rounded-full ${
              isRunning ? "bg-accent-forest animate-pulse" : "bg-status-warning"
            }`}
          />
          <span className="uppercase tracking-wider font-mono text-[10.5px]">
            {state.mode === "replay" ? "Replay Simulation" : state.mode === "demo" ? "Demo Scenario" : "Live Stream"}
          </span>
          <span className="text-foreground-muted">·</span>
          <span className="text-foreground-muted capitalize">{state.status}</span>
        </div>

        <span className="hidden lg:inline-flex items-center text-[11.5px] text-foreground-muted">
          Simulated plant telemetry · Not live sensors
        </span>
      </div>

      {/* Center: Simulated Clock */}
      <div className="flex items-center gap-2 rounded-md border border-border-subtle bg-surface px-3 py-1 font-mono text-xs shadow-[0_1px_2px_rgba(37,41,35,0.02)]">
        <Clock className="size-3.5 text-accent-forest" />
        <span className="text-foreground-muted font-sans text-[11px] uppercase tracking-wider font-semibold">
          Sim Clock:
        </span>
        <span className="font-bold text-foreground tabular-nums text-sm">
          {formattedTime}
        </span>
        <span className="text-[11px] text-foreground-muted">
          (Tick #{state.step_count || 1})
        </span>
      </div>

      {/* Right: Controls & Failure Injection */}
      <div className="flex items-center gap-2">
        {/* Play / Pause */}
        {isRunning ? (
          <button
            type="button"
            onClick={onPause}
            disabled={isLoading}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-normal bg-surface px-2.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors disabled:opacity-50"
            title="Pause simulation clock"
          >
            <Pause className="size-3.5 text-accent-terracotta" />
            <span className="hidden sm:inline">Pause</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={onResume}
            disabled={isLoading}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-accent-forest-border bg-accent-forest-subtle px-2.5 text-xs font-bold text-accent-forest hover:bg-accent-forest-subtle/80 transition-colors disabled:opacity-50"
            title="Resume simulation clock"
          >
            <Play className="size-3.5 fill-current" />
            <span className="hidden sm:inline">Resume</span>
          </button>
        )}

        {/* Step Button */}
        <button
          type="button"
          onClick={() => onStep(1)}
          disabled={isLoading}
          className="inline-flex h-8 items-center gap-1 rounded-md border border-border-normal bg-surface px-2.5 text-xs font-semibold text-foreground hover:bg-surface-hover hover:border-border-strong transition-colors disabled:opacity-50"
          title="Advance simulation by 1 step (10 minutes)"
        >
          <SkipForward className="size-3.5 text-foreground-muted" />
          <span>Step +10m</span>
        </button>

        {/* Reset Button */}
        <button
          type="button"
          onClick={onReset}
          disabled={isLoading}
          className="inline-flex h-8 items-center justify-center size-8 rounded-md border border-border-normal bg-surface text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors disabled:opacity-50"
          title="Reset simulation to baseline"
        >
          <RotateCcw className="size-3.5" />
        </button>

        {/* Scenario Injection Trigger */}
        <button
          type="button"
          onClick={onOpenFailureModal}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-status-critical-border bg-status-critical-bg px-3 text-xs font-bold text-status-critical hover:bg-status-critical-bg/80 transition-colors shadow-sm"
          title="Inject emergency anomaly scenario for live demonstration"
        >
          <Zap className="size-3.5 fill-current" />
          <span>Inject Anomaly</span>
        </button>
      </div>
    </div>
  );
};
