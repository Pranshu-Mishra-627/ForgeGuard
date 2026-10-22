"use client";
import React, { useState } from "react";
import {
  Activity,
  AlertCircle,
  CalendarCheck,
  ShieldAlert,
  Zap,
  Filter,
  Search,
  CheckCircle2,
  Clock,
  User,
  Cpu,
} from "lucide-react";
import { AuditTrailEvent, EventSeverity, EventCategory } from "@/types/api";

interface AuditLogViewProps {
  events: AuditTrailEvent[];
  onSelectMachineId?: (machineId: string) => void;
  onSelectJobId?: (jobId: string) => void;
}

export const AuditLogView: React.FC<AuditLogViewProps> = ({
  events,
  onSelectMachineId,
  onSelectJobId,
}) => {
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredEvents = events.filter((e) => {
    if (severityFilter !== "all" && e.severity !== severityFilter) return false;
    if (categoryFilter !== "all" && e.category !== categoryFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchText = `${e.title} ${e.message} ${e.machine_id ?? ""} ${e.job_id ?? ""}`.toLowerCase();
      if (!matchText.includes(q)) return false;
    }
    return true;
  });

  const getSeverityBadge = (sev: EventSeverity) => {
    switch (sev) {
      case "critical":
        return "bg-status-critical-bg text-status-critical border-status-critical-border";
      case "warning":
        return "bg-status-warning-bg text-status-warning border-status-warning-border";
      case "decision":
        return "bg-accent-forest-subtle text-accent-forest border-accent-forest-border";
      case "info":
      default:
        return "bg-surface-subtle text-foreground-muted border-border-normal";
    }
  };

  const getCategoryIcon = (cat: EventCategory) => {
    switch (cat) {
      case "preemption":
        return Zap;
      case "safety":
        return ShieldAlert;
      case "schedule":
        return CalendarCheck;
      case "prediction":
        return Cpu;
      case "job":
        return Activity;
      default:
        return Clock;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls Bar */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle pb-4">
          <div>
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Operational Event Stream & Audit Trail
            </h2>
            <p className="text-[13px] text-foreground-muted mt-0.5">
              Immutable chronological log of model inference, safety blocks, schedule updates, and pre-emption executions.
            </p>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-foreground-muted" />
            <input
              type="text"
              placeholder="Search events, assets, jobs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 w-full rounded-md border border-border-normal bg-surface pl-9 pr-3 text-xs sm:text-sm text-foreground focus-visible:outline-none focus-visible:border-accent-forest"
            />
          </div>
        </div>

        {/* Filter Buttons */}
        <div className="flex flex-wrap items-center justify-between gap-4 text-xs">
          {/* Severity Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold text-foreground">Severity:</span>
            {["all", "critical", "decision", "warning", "info"].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSeverityFilter(s)}
                className={`rounded-md border px-3 py-1.5 font-semibold capitalize transition-colors ${
                  severityFilter === s
                    ? "bg-surface-raised text-foreground border-border-strong shadow-sm font-bold"
                    : "bg-surface text-foreground-muted hover:text-foreground border-border-normal"
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Category Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold text-foreground">Category:</span>
            {["all", "prediction", "preemption", "safety", "schedule", "job"].map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCategoryFilter(c)}
                className={`rounded-md border px-3 py-1.5 font-semibold capitalize transition-colors ${
                  categoryFilter === c
                    ? "bg-surface-raised text-foreground border-border-strong shadow-sm font-bold"
                    : "bg-surface text-foreground-muted hover:text-foreground border-border-normal"
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Events List */}
      <div className="panel divide-y divide-border-subtle bg-surface border border-border-normal overflow-hidden">
        {filteredEvents.length === 0 ? (
          <div className="py-12 text-center text-sm text-foreground-muted">
            No events found matching current filter criteria.
          </div>
        ) : (
          filteredEvents.map((evt) => {
            const Icon = getCategoryIcon(evt.category);
            const dateStr = new Date(evt.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });

            return (
              <div
                key={evt.id}
                className="p-5 sm:p-6 hover:bg-surface-hover/70 transition-colors flex items-start gap-4"
              >
                <div
                  className={`flex size-9 items-center justify-center rounded-md border shrink-0 mt-0.5 ${getSeverityBadge(
                    evt.severity
                  )}`}
                >
                  <Icon className="size-4.5" />
                </div>

                <div className="flex-1 space-y-1.5 min-w-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-foreground text-sm sm:text-base">
                        {evt.title}
                      </span>
                      <span
                        className={`font-mono text-xs font-bold px-2 py-0.5 rounded border uppercase ${getSeverityBadge(
                          evt.severity
                        )}`}
                      >
                        {evt.severity}
                      </span>
                      <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-surface-subtle border border-border-subtle text-foreground-muted uppercase">
                        {evt.category}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs font-mono text-foreground-muted">
                      <Clock className="size-3.5" />
                      <span>{dateStr}</span>
                    </div>
                  </div>

                  <p className="text-[13.5px] leading-relaxed text-foreground">
                    {evt.message}
                  </p>

                  {/* Context Tags */}
                  <div className="flex flex-wrap items-center gap-3 pt-1 text-xs font-mono">
                    <span className="text-foreground-muted">
                      Actor: <strong className="text-foreground capitalize">{evt.actor}</strong>
                    </span>
                    {evt.machine_id && (
                      <button
                        type="button"
                        onClick={() => onSelectMachineId && onSelectMachineId(evt.machine_id!)}
                        className="font-bold text-accent-forest hover:underline"
                      >
                        Asset: {evt.machine_id}
                      </button>
                    )}
                    {evt.job_id && (
                      <button
                        type="button"
                        onClick={() => onSelectJobId && onSelectJobId(evt.job_id!)}
                        className="font-bold text-accent-terracotta hover:underline"
                      >
                        Order: {evt.job_id}
                      </button>
                    )}
                    {evt.technician_id && (
                      <span className="text-foreground-muted">
                        Crew: <strong className="text-foreground">{evt.technician_id}</strong>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
