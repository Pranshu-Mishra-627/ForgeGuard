"use client";
import React, { useState, useMemo } from "react";
import { Search, ArrowUpDown, ChevronDown } from "lucide-react";
import { Machine, RiskLevel } from "@/lib/types";

interface MachineRiskTableProps {
  machines: Machine[];
  statusById: Map<string, "scheduled" | "deferred">;
  onSelectMachine: (m: Machine) => void;
  className?: string;
  maxHeight?: string;
  lines?: string[];
  filterRisk?: RiskLevel | "all";
  onRiskFilterChange?: (risk: RiskLevel | "all") => void;
}

export const MachineRiskTable: React.FC<MachineRiskTableProps> = ({
  machines,
  statusById,
  onSelectMachine,
  className = "",
  maxHeight = "max-h-[460px]",
  lines = [],
  filterRisk: externalFilterRisk,
  onRiskFilterChange,
}) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [internalFilterRisk, setInternalFilterRisk] = useState<RiskLevel | "all">("all");
  const [filterLine, setFilterLine] = useState<string>("all");
  const [sortKey, setSortKey] = useState<"priority" | "probability">("priority");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const currentFilterRisk =
    externalFilterRisk !== undefined ? externalFilterRisk : internalFilterRisk;

  const handleRiskChange = (val: RiskLevel | "all") => {
    if (onRiskFilterChange) {
      onRiskFilterChange(val);
    } else {
      setInternalFilterRisk(val);
    }
  };

  // Derive unique lines if not passed
  const availableLines = useMemo(() => {
    if (lines.length > 0) return lines;
    return Array.from(new Set(machines.map((m) => m.line))).sort();
  }, [machines, lines]);

  // Filtering & Sorting
  const filteredMachines = useMemo(() => {
    return machines
      .filter((m) => {
        if (currentFilterRisk !== "all" && m.risk !== currentFilterRisk) return false;
        if (filterLine !== "all" && m.line !== filterLine) return false;
        if (searchTerm.trim()) {
          const q = searchTerm.toLowerCase();
          const matchId = m.id.toLowerCase().includes(q);
          const matchType = m.type.toLowerCase().includes(q);
          const matchMode = m.failureMode.toLowerCase().includes(q);
          const matchLine = m.line.toLowerCase().includes(q);
          if (!matchId && !matchType && !matchMode && !matchLine) return false;
        }
        return true;
      })
      .sort((a, b) => {
        const factor = sortDir === "desc" ? -1 : 1;
        if (sortKey === "priority") {
          return (a.priority - b.priority) * factor;
        } else {
          return (a.probability - b.probability) * factor;
        }
      });
  }, [machines, currentFilterRisk, filterLine, searchTerm, sortKey, sortDir]);

  const toggleSort = (key: "priority" | "probability") => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const getRiskBadge = (risk: RiskLevel) => {
    switch (risk) {
      case "critical":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 font-mono text-xs font-semibold uppercase text-status-critical bg-status-critical-bg border border-status-critical-border">
            <span className="size-2 rounded-full bg-status-critical" />
            Critical
          </span>
        );
      case "high":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 font-mono text-xs font-semibold uppercase text-status-warning bg-status-warning-bg border border-status-warning-border">
            <span className="size-2 rounded-full bg-status-warning" />
            High
          </span>
        );
      case "medium":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 font-mono text-xs font-semibold uppercase text-accent-forest bg-accent-forest-subtle border border-accent-forest-border">
            <span className="size-2 rounded-full bg-accent-forest" />
            Medium
          </span>
        );
      case "low":
        return (
          <span className="inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 font-mono text-xs font-semibold uppercase text-foreground-muted bg-surface-subtle border border-border-normal">
            <span className="size-2 rounded-full bg-foreground-muted" />
            Low
          </span>
        );
    }
  };

  return (
    <section className={`panel flex flex-col overflow-hidden shadow-sm ${className}`}>
      {/* Table Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-normal px-6 py-4.5">
        <div>
          <h2 className="text-[18px] font-bold tracking-tight text-foreground">
            Machine Risk Ranking
          </h2>
          <p className="mt-1 text-[13px] text-foreground-muted">
            {filteredMachines.length} of {machines.length} monitored machines · sorted by{" "}
            {sortKey === "priority" ? "cost-weighted priority score" : "failure probability"}
          </p>
        </div>
      </div>

      {/* Controls Bar: Search & Filters */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle bg-surface-subtle px-6 py-3.5">
        {/* Search */}
        <div className="relative min-w-52 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-foreground-muted" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter by ID, machine type, line..."
            className="h-10 w-full rounded-[4px] border border-border-normal bg-surface pl-9 pr-3 text-[13.5px] text-foreground placeholder:text-foreground-muted focus-visible:border-accent-forest focus-visible:outline-none shadow-[0_1px_2px_rgba(41,43,40,0.02)]"
          />
        </div>

        {/* Risk Filter */}
        <div className="relative">
          <select
            aria-label="Filter by risk level"
            value={currentFilterRisk}
            onChange={(e) => handleRiskChange(e.target.value as RiskLevel | "all")}
            className="h-10 appearance-none rounded-[4px] border border-border-normal bg-surface px-3.5 pr-8.5 text-[13.5px] font-medium text-foreground focus-visible:border-accent-forest focus-visible:outline-none shadow-[0_1px_2px_rgba(41,43,40,0.02)]"
          >
            <option value="all">All risk tiers</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 text-foreground-muted" />
        </div>

        {/* Line Filter */}
        <div className="relative">
          <select
            aria-label="Filter by production line"
            value={filterLine}
            onChange={(e) => setFilterLine(e.target.value)}
            className="h-10 appearance-none rounded-[4px] border border-border-normal bg-surface px-3.5 pr-8.5 text-[13.5px] font-medium text-foreground focus-visible:border-accent-forest focus-visible:outline-none shadow-[0_1px_2px_rgba(41,43,40,0.02)]"
          >
            <option value="all">All lines</option>
            {availableLines.map((line) => (
              <option key={line} value={line}>
                {line}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-3.5 -translate-y-1/2 text-foreground-muted" />
        </div>
      </div>

      {/* Data Table */}
      <div className={`overflow-auto ${maxHeight}`}>
        <table className="w-full min-w-[960px] border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-surface-subtle border-b border-border-normal">
            <tr className="eyebrow h-11 text-foreground-muted select-none text-xs">
              <th scope="col" className="pl-6 pr-4 font-semibold">
                Machine ID & Line
              </th>
              <th scope="col" className="px-4 font-semibold">
                <button
                  type="button"
                  onClick={() => toggleSort("probability")}
                  className="inline-flex items-center gap-1.5 hover:text-foreground focus-visible:outline-none"
                >
                  Failure Prob.
                  <ArrowUpDown className="size-3.5 text-foreground-muted" />
                </button>
              </th>
              <th scope="col" className="px-4 font-semibold">
                Predicted Failure Mode
              </th>
              <th scope="col" className="px-4 font-semibold">
                Risk Tier
              </th>
              <th scope="col" className="px-4 font-semibold text-right">
                Asset Failure Loss
              </th>
              <th scope="col" className="px-4 font-semibold">
                Recommended Action
              </th>
              <th scope="col" className="pl-4 pr-6 text-right font-semibold">
                <button
                  type="button"
                  onClick={() => toggleSort("priority")}
                  className="inline-flex items-center gap-1.5 text-accent-forest hover:underline focus-visible:outline-none font-semibold"
                >
                  Priority Score
                  <ArrowUpDown className="size-3.5" />
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle bg-surface">
            {filteredMachines.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-sm text-foreground-muted">
                  No machines match the selected filters.
                </td>
              </tr>
            ) : (
              filteredMachines.map((m) => {
                const status = statusById.get(m.id);
                return (
                  <tr
                    key={m.id}
                    tabIndex={0}
                    onClick={() => onSelectMachine(m)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectMachine(m);
                      }
                    }}
                    className="group cursor-pointer transition-colors hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none"
                  >
                    {/* Machine ID, Equipment Type, Line, Schedule badge */}
                    <td className="py-3.5 pl-6 pr-4">
                      <div className="flex items-center gap-2.5">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[14px] font-bold text-foreground">
                              {m.id}
                            </span>
                            {status === "scheduled" && (
                              <span className="inline-flex items-center rounded-[3px] px-1.5 py-0.5 font-mono text-xs uppercase tracking-wider text-status-healthy bg-status-healthy-bg border border-status-healthy-border font-semibold">
                                Sched
                              </span>
                            )}
                            {status === "deferred" && (
                              <span className="inline-flex items-center rounded-[3px] px-1.5 py-0.5 font-mono text-xs uppercase tracking-wider text-status-warning bg-status-warning-bg border border-status-warning-border font-semibold">
                                Defer
                              </span>
                            )}
                          </div>
                          <p className="truncate text-[12.5px] text-foreground-muted mt-0.5">
                            {m.type} · {m.line}
                          </p>
                        </div>
                      </div>
                    </td>

                    {/* Failure Probability + Micro Bar */}
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2.5 font-mono tabular-nums text-sm">
                        <span
                          className={`w-12 text-right font-bold ${
                            m.risk === "critical"
                              ? "text-status-critical"
                              : m.risk === "high"
                              ? "text-status-warning"
                              : m.risk === "medium"
                              ? "text-accent-forest"
                              : "text-foreground-muted"
                          }`}
                        >
                          {(m.probability * 100).toFixed(1)}%
                        </span>
                        <div
                          className="h-2 w-14 overflow-hidden rounded-full bg-surface-subtle border border-border-subtle"
                          aria-hidden="true"
                        >
                          <div
                            className={`h-full rounded-full ${
                              m.risk === "critical"
                                ? "bg-status-critical"
                                : m.risk === "high"
                                ? "bg-status-warning"
                                : m.risk === "medium"
                                ? "bg-accent-forest"
                                : "bg-foreground-muted"
                            }`}
                            style={{ width: `${m.probability * 100}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Predicted Mode */}
                    <td className="px-4 py-3.5 text-foreground whitespace-nowrap font-medium text-[13.5px]">
                      {m.failureMode}
                    </td>

                    {/* Risk Badge */}
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      {getRiskBadge(m.risk)}
                    </td>

                    {/* Asset Failure Loss */}
                    <td className="px-4 py-3.5 text-right font-mono tabular-nums text-sm text-foreground font-semibold">
                      ${(m.failureCost / 1000).toFixed(0)}k
                    </td>

                    {/* Recommendation */}
                    <td className="max-w-xs xl:max-w-md px-4 py-3.5 text-foreground-muted">
                      <p className="truncate group-hover:text-foreground text-[13px] leading-relaxed" title={m.recommendation}>
                        {m.recommendation}
                      </p>
                    </td>

                    {/* Priority Score */}
                    <td className="py-3.5 pl-4 pr-6 text-right">
                      <div className="flex items-center justify-end gap-2.5 font-mono tabular-nums">
                        <div
                          className="h-2 w-12 overflow-hidden rounded-full bg-surface-subtle border border-border-subtle"
                          aria-hidden="true"
                        >
                          <div
                            className="h-full rounded-full bg-accent-forest"
                            style={{ width: `${m.priority}%` }}
                          />
                        </div>
                        <span className="w-6 text-right font-bold text-sm text-foreground">
                          {m.priority}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};
