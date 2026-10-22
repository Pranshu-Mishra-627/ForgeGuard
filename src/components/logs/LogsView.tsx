"use client";
import React, { useState } from "react";
import { Machine, DecisionLogEvent } from "@/lib/types";
import { ActivityFeed } from "../overview/ActivityFeed";
import { MachineRiskTable } from "../overview/MachineRiskTable";
import { Filter } from "lucide-react";

interface LogsViewProps {
  events: DecisionLogEvent[];
  machines: Machine[];
  statusById: Map<string, "scheduled" | "deferred">;
  onSelectMachine: (m: Machine) => void;
}

export const LogsView: React.FC<LogsViewProps> = ({
  events,
  machines,
  statusById,
  onSelectMachine,
}) => {
  const [filterKind, setFilterKind] = useState<string>("all");

  const filteredEvents =
    filterKind === "all"
      ? events
      : events.filter((e) => e.kind === filterKind);

  return (
    <div className="space-y-6">
      {/* Event Filter Bar */}
      <div className="panel p-4 sm:p-5 bg-surface flex flex-wrap items-center justify-between gap-4 text-xs border border-border-normal">
        <div className="flex items-center gap-2.5 text-foreground-muted">
          <Filter className="size-4 text-foreground-muted" />
          <span className="font-bold text-foreground text-sm">Filter Pipeline Events:</span>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter events">
          {["all", "prediction", "alert", "schedule", "system"].map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => setFilterKind(kind)}
              className={`h-9 rounded-md border px-3.5 text-xs font-semibold capitalize transition-colors focus-visible:outline-none ${
                filterKind === kind
                  ? "bg-surface-raised text-foreground border-border-strong shadow-[0_1px_2px_rgba(37,41,35,0.06)]"
                  : "bg-surface text-foreground-muted hover:bg-surface-hover hover:text-foreground border-border-normal"
              }`}
            >
              {kind === "all" ? "All Events" : kind}
            </button>
          ))}
        </div>
      </div>

      {/* Main Grid: Activity Feed (5 cols) + Machine Table (7 cols) */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-5">
          <ActivityFeed
            events={filteredEvents}
            listHeight="max-h-[calc(100vh-230px)]"
          />
        </div>
        <div className="xl:col-span-7">
          <MachineRiskTable
            machines={machines}
            statusById={statusById}
            onSelectMachine={onSelectMachine}
            maxHeight="max-h-[calc(100vh-230px)]"
          />
        </div>
      </div>
    </div>
  );
};
