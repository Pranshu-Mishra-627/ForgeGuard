"use client";
import React from "react";
import { Play, Loader2, ChevronDown, Menu } from "lucide-react";
import { PLANTS, SHIFTS } from "@/lib/data-generator";
import { NavView } from "./Sidebar";

interface TopHeaderProps {
  currentView: NavView;
  onViewChange: (view: NavView) => void;
  selectedPlant: string;
  onPlantChange: (plant: string) => void;
  selectedShift: string;
  onShiftChange: (shift: string) => void;
  onRunShiftAnalysis: () => void;
  isScoring: boolean;
  lastUpdated: string;
  onOpenMobile?: () => void;
}

const VIEW_HEADINGS: Record<NavView, { title: string; subtitle: string }> = {
  overview: {
    title: "Command Overview",
    subtitle: "Plant health status, urgent machinery ranking, active operations, and technician allocation",
  },
  machines: {
    title: "Machine Monitor & Safety",
    subtitle: "Telemetry health, multi-sensor inference, failure modes, and safety classifications",
  },
  schedule: {
    title: "Shift Schedule & Gantt Timeline",
    subtitle: "Deterministic technician allocation across the 8-hour shift envelope with conflict resolution",
  },
  jobs: {
    title: "Maintenance Work Orders",
    subtitle: "Kanban dispatch board, progress tracking, and emergency pre-emption evaluation gate",
  },
  technicians: {
    title: "Technician Resource Command",
    subtitle: "Specialist availability, active assignments, skill certifications, and crew workload",
  },
  cost: {
    title: "Cost Analysis & Alternatives",
    subtitle: "Side-by-side scheduling options, downtime risk exposure, and economic optimization models",
  },
  logs: {
    title: "Event Stream & Audit Trail",
    subtitle: "Chronological log of model inference, safety blocks, schedule updates, and pre-emption executions",
  },
  engine: {
    title: "Three-Stage Decision Engine",
    subtitle: "Predictive inference, cost-aware optimization, and capacity dispatch framework",
  },
};

export const TopHeader: React.FC<TopHeaderProps> = ({
  currentView,
  onViewChange,
  selectedPlant,
  onPlantChange,
  selectedShift,
  onShiftChange,
  onRunShiftAnalysis,
  isScoring,
  lastUpdated,
  onOpenMobile,
}) => {
  const currentHeading = VIEW_HEADINGS[currentView] ?? VIEW_HEADINGS.overview;

  return (
    <header className="sticky top-0 z-30 border-b border-border-normal bg-background/95 backdrop-blur-sm">
      <div className="flex min-h-16 flex-wrap items-center justify-between gap-x-6 gap-y-3 px-6 py-3 lg:px-8">
        {/* Title & Editorial Context */}
        <div className="flex items-center gap-3.5 min-w-0">
          {onOpenMobile && (
            <button
              type="button"
              onClick={onOpenMobile}
              className="flex size-9 items-center justify-center rounded border border-border-normal text-foreground-muted hover:text-foreground md:hidden"
              aria-label="Open navigation menu"
            >
              <Menu className="size-4.5" />
            </button>
          )}

          <div className="min-w-0">
            <h1 className="text-2xl sm:text-[26px] font-bold tracking-tight text-foreground leading-tight">
              {currentHeading.title}
            </h1>
            <p className="mt-1 hidden truncate text-[13.5px] text-foreground-muted lg:block">
              {currentHeading.subtitle}
            </p>
          </div>
        </div>

        {/* Operational Controls Area */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Plant Selector */}
          <div className="relative">
            <select
              aria-label="Plant"
              value={selectedPlant}
              onChange={(e) => onPlantChange(e.target.value)}
              className="h-10 w-52 appearance-none rounded-[4px] border border-border-normal bg-surface px-3.5 pr-9 text-[13.5px] font-medium text-foreground focus-visible:border-accent-forest focus-visible:outline-none shadow-[0_1px_2px_rgba(41,43,40,0.03)]"
            >
              {PLANTS.map((p) => (
                <option key={p.value} value={p.value} className="bg-surface text-foreground">
                  {p.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-foreground-muted" />
          </div>

          {/* Shift Selector */}
          <div className="relative">
            <select
              aria-label="Shift"
              value={selectedShift}
              onChange={(e) => onShiftChange(e.target.value)}
              className="h-10 w-44 appearance-none rounded-[4px] border border-border-normal bg-surface px-3.5 pr-9 text-[13.5px] font-medium text-foreground focus-visible:border-accent-forest focus-visible:outline-none shadow-[0_1px_2px_rgba(41,43,40,0.03)]"
            >
              {SHIFTS.map((s) => (
                <option key={s.value} value={s.value} className="bg-surface text-foreground">
                  {s.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-foreground-muted" />
          </div>

          {/* Timestamp Indicator */}
          <div
            className="hidden h-10 items-center gap-2 rounded-[4px] border border-border-normal bg-surface px-3.5 text-xs text-foreground-muted xl:flex shadow-[0_1px_2px_rgba(41,43,40,0.03)]"
            aria-live="polite"
          >
            <span className="size-2 rounded-full bg-accent-forest" />
            <span>
              Updated <span className="font-mono text-foreground font-semibold">{lastUpdated}</span>
            </span>
          </div>

          {/* Primary Action Button: Run Shift Analysis */}
          <button
            type="button"
            onClick={onRunShiftAnalysis}
            disabled={isScoring}
            className="inline-flex h-10 items-center gap-2.5 rounded-[4px] bg-accent-forest px-4 text-[13.5px] font-semibold text-white transition-colors hover:bg-[#435948] active:bg-[#384A3C] disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-forest shadow-[0_1px_2px_rgba(41,43,40,0.08)]"
          >
            {isScoring ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Scoring fleet...
              </>
            ) : (
              <>
                <Play className="size-3.5 fill-current" />
                Run Shift Analysis
              </>
            )}
          </button>
        </div>
      </div>

      {/* Mobile Horizontal Navigation Pills */}
      <nav aria-label="Sections" className="flex gap-1 overflow-x-auto border-t border-border-subtle px-3 py-1.5 md:hidden">
        {(["overview", "machines", "schedule", "jobs", "technicians", "cost", "logs", "engine"] as NavView[]).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onViewChange(v)}
            className={`shrink-0 rounded-[3px] px-2.5 py-1 text-xs capitalize ${
              currentView === v
                ? "bg-surface-raised font-medium text-foreground border border-border-normal shadow-[0_1px_1px_rgba(41,43,40,0.04)]"
                : "text-foreground-muted hover:text-foreground"
            }`}
          >
            {v === "overview"
              ? "Overview"
              : v === "machines"
              ? "Machines"
              : v === "schedule"
              ? "Schedule"
              : v === "jobs"
              ? "Jobs"
              : v === "technicians"
              ? "Technicians"
              : v === "cost"
              ? "Cost"
              : v === "logs"
              ? "Logs"
              : "Engine"}
          </button>
        ))}
      </nav>
    </header>
  );
};
