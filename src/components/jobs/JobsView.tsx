"use client";
import React, { useState } from "react";
import {
  Wrench,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Play,
  Pause,
  Clock,
  Columns,
  Table as TableIcon,
  Zap,
  ArrowRight,
  Filter,
} from "lucide-react";
import { JobContract, JobPriority, JobStatus } from "@/types/api";
import { formatCurrency } from "@/lib/data-generator";

interface JobsViewProps {
  jobs: JobContract[];
  onSelectJob: (job: JobContract) => void;
  onEvaluatePreemption: (activeJob: JobContract) => void;
}

export const JobsView: React.FC<JobsViewProps> = ({
  jobs,
  onSelectJob,
  onEvaluatePreemption,
}) => {
  const [viewMode, setViewMode] = useState<"table" | "kanban">("table");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const inProgressJobs = jobs.filter((j) => j.status === "in_progress");
  const queuedJobs = jobs.filter((j) => j.status === "queued");
  const assignedJobs = jobs.filter((j) => j.status === "assigned");
  const pausedJobs = jobs.filter((j) => j.status === "paused");
  const completedJobs = jobs.filter((j) => j.status === "completed");

  const filteredJobs =
    statusFilter === "all" ? jobs : jobs.filter((j) => j.status === statusFilter);

  return (
    <div className="space-y-6">
      {/* KPI Summary Banner */}
      <div className="panel p-5 sm:p-6 bg-surface grid grid-cols-2 lg:grid-cols-4 gap-4 divide-y lg:divide-y-0 lg:divide-x divide-border-subtle border border-border-normal">
        <div className="sm:px-4">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Active Work Orders
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-forest mt-1.5 block">
            {inProgressJobs.length} active
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Currently on shop floor
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Queued Backlog
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground mt-1.5 block">
            {queuedJobs.length + assignedJobs.length} jobs
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Awaiting start window
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Paused / Pre-empted
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-terracotta mt-1.5 block">
            {pausedJobs.length} interrupted
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Progress preserved
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Completed This Shift
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground mt-1.5 block">
            {completedJobs.length} orders
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Verified & closed
          </span>
        </div>
      </div>

      {/* Control Strip & Filters */}
      <div className="panel p-4 sm:p-5 bg-surface border border-border-normal flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-foreground-muted text-xs">
            <Filter className="size-4" />
            <span className="font-bold text-foreground">Status Filter:</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { id: "all", label: "All Work Orders" },
              { id: "in_progress", label: "In Progress" },
              { id: "queued", label: "Queued" },
              { id: "paused", label: "Pre-empted / Paused" },
              { id: "completed", label: "Completed" },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStatusFilter(f.id)}
                className={`rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
                  statusFilter === f.id
                    ? "bg-surface-raised text-foreground border-border-strong shadow-sm font-bold"
                    : "bg-surface text-foreground-muted hover:text-foreground border-border-normal"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* View Mode Toggle */}
        <div className="inline-flex rounded-md border border-border-normal bg-surface p-1 text-xs">
          <button
            type="button"
            onClick={() => setViewMode("table")}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
              viewMode === "table"
                ? "bg-surface-raised text-foreground shadow-sm font-bold"
                : "text-foreground-muted hover:text-foreground"
            }`}
          >
            <TableIcon className="size-3.5" />
            <span>Table View</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("kanban")}
            className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
              viewMode === "kanban"
                ? "bg-surface-raised text-foreground shadow-sm font-bold"
                : "text-foreground-muted hover:text-foreground"
            }`}
          >
            <Columns className="size-3.5" />
            <span>Kanban Board</span>
          </button>
        </div>
      </div>

      {/* Main Content: Table View vs Kanban Board */}
      {viewMode === "table" ? (
        <div className="panel overflow-hidden bg-surface border border-border-normal">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse min-w-[960px]">
              <thead className="bg-surface-subtle border-b border-border-normal eyebrow h-11 text-foreground-muted">
                <tr>
                  <th className="px-5 font-bold">Job ID</th>
                  <th className="px-4 font-bold">Asset Target</th>
                  <th className="px-4 font-bold">Priority</th>
                  <th className="px-4 font-bold">Assigned Specialist</th>
                  <th className="px-4 font-bold">Progress / Elapsed</th>
                  <th className="px-4 font-bold">Safety Hard Gate</th>
                  <th className="px-4 font-bold">Failure Exposure</th>
                  <th className="px-5 font-bold text-right">Operational Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle bg-surface">
                {filteredJobs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-sm text-foreground-muted">
                      No maintenance work orders found matching this filter.
                    </td>
                  </tr>
                ) : (
                  filteredJobs.map((job) => {
                    const isCritical = job.priority === "critical";
                    const isInProgress = job.status === "in_progress";

                    return (
                      <tr
                        key={job.job_id}
                        className="hover:bg-surface-hover cursor-pointer transition-colors"
                        onClick={() => onSelectJob(job)}
                      >
                        <td className="px-5 py-3.5">
                          <span className="font-mono font-bold text-foreground text-sm block">
                            {job.job_id}
                          </span>
                          <span className="text-xs text-foreground-muted block capitalize">
                            {job.job_type}
                          </span>
                        </td>

                        <td className="px-4 py-3.5">
                          <span className="font-mono font-bold text-foreground block">
                            {job.machine_id}
                          </span>
                          <span className="text-xs text-foreground-muted truncate block max-w-44">
                            {job.machine_name}
                          </span>
                        </td>

                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-flex items-center rounded px-2.5 py-0.5 font-mono text-xs font-bold uppercase border ${
                              isCritical
                                ? "bg-status-critical-bg text-status-critical border-status-critical-border"
                                : job.priority === "high"
                                ? "bg-status-warning-bg text-status-warning border-status-warning-border"
                                : "bg-surface-subtle text-foreground-muted border-border-normal"
                            }`}
                          >
                            {job.priority}
                          </span>
                        </td>

                        <td className="px-4 py-3.5 font-medium text-foreground">
                          {job.technician_name ? (
                            <span>{job.technician_name}</span>
                          ) : (
                            <span className="text-foreground-muted italic text-xs">Unassigned</span>
                          )}
                        </td>

                        {/* Progress */}
                        <td className="px-4 py-3.5">
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-xs font-mono text-foreground-muted">
                              <span>{job.progress_percent}%</span>
                              <span>{job.elapsed_minutes}/{job.estimated_duration_minutes}m</span>
                            </div>
                            <div className="h-2 w-32 rounded bg-surface-subtle border border-border-subtle overflow-hidden">
                              <div
                                style={{ width: `${job.progress_percent}%` }}
                                className={`h-full ${
                                  job.status === "paused"
                                    ? "bg-accent-terracotta"
                                    : job.status === "completed"
                                    ? "bg-accent-forest"
                                    : "bg-foreground"
                                }`}
                              />
                            </div>
                          </div>
                        </td>

                        {/* Safety Status */}
                        <td className="px-4 py-3.5">
                          <span
                            className={`inline-flex items-center gap-1 font-mono text-xs font-bold px-2.5 py-0.5 rounded border uppercase ${
                              job.safety_status === "safe"
                                ? "text-accent-forest bg-accent-forest-subtle border-accent-forest-border"
                                : job.safety_status === "unsafe"
                                ? "text-status-critical bg-status-critical-bg border-status-critical-border"
                                : "text-status-warning bg-status-warning-bg border-status-warning-border"
                            }`}
                          >
                            {job.safety_status === "safe" ? (
                              <ShieldCheck className="size-3" />
                            ) : (
                              <ShieldAlert className="size-3" />
                            )}
                            {job.safety_status}
                          </span>
                        </td>

                        <td className="px-4 py-3.5 font-mono text-sm font-semibold text-foreground">
                          {formatCurrency(job.estimated_downtime_cost)}
                        </td>

                        {/* Actions */}
                        <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                          {isInProgress ? (
                            <button
                              type="button"
                              onClick={() => onEvaluatePreemption(job)}
                              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-accent-terracotta-border bg-accent-terracotta-subtle px-3 text-xs font-bold text-accent-terracotta hover:bg-accent-terracotta-subtle/80 transition-colors shadow-sm"
                              title="Evaluate whether this active job can be interrupted for a critical task"
                            >
                              <Zap className="size-3.5" />
                              <span>Evaluate Pre-emption</span>
                            </button>
                          ) : job.status === "paused" ? (
                            <span className="font-mono text-xs font-bold text-accent-terracotta uppercase">
                              Pre-empted
                            </span>
                          ) : (
                            <span className="text-xs text-foreground-muted font-mono capitalize">
                              {job.status}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Kanban Board View */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { title: "Queued Backlog", list: queuedJobs, badgeClass: "bg-surface text-foreground" },
            { title: "In Progress (Active)", list: inProgressJobs, badgeClass: "bg-accent-forest text-white" },
            { title: "Paused / Pre-empted", list: pausedJobs, badgeClass: "bg-accent-terracotta text-white" },
            { title: "Completed", list: completedJobs, badgeClass: "bg-surface-subtle text-foreground-muted" },
          ].map((col) => (
            <div key={col.title} className="panel p-4 bg-surface border border-border-normal space-y-3">
              <div className="flex items-center justify-between border-b border-border-subtle pb-2.5">
                <span className="font-bold text-foreground text-[13.5px]">{col.title}</span>
                <span className={`font-mono text-xs font-bold px-2 py-0.5 rounded ${col.badgeClass}`}>
                  {col.list.length}
                </span>
              </div>

              <div className="space-y-3 min-h-[300px]">
                {col.list.map((job) => (
                  <div
                    key={job.job_id}
                    onClick={() => onSelectJob(job)}
                    className="rounded-md border border-border-normal bg-surface p-3.5 shadow-sm space-y-2 hover:border-border-strong cursor-pointer transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-xs text-foreground">
                        {job.job_id}
                      </span>
                      <span
                        className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded uppercase border ${
                          job.priority === "critical"
                            ? "bg-status-critical-bg text-status-critical border-status-critical-border"
                            : "bg-surface-subtle text-foreground-muted border-border-normal"
                        }`}
                      >
                        {job.priority}
                      </span>
                    </div>

                    <h4 className="font-bold text-foreground text-xs leading-snug line-clamp-2">
                      {job.machine_name}
                    </h4>

                    <p className="text-[11.5px] text-foreground-muted line-clamp-2">
                      {job.description}
                    </p>

                    <div className="flex items-center justify-between text-xs pt-2 border-t border-border-subtle text-foreground-muted font-mono">
                      <span>{job.technician_name ? job.technician_name.split(" ")[0] : "No Tech"}</span>
                      <span>{job.progress_percent}%</span>
                    </div>

                    {job.status === "in_progress" && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onEvaluatePreemption(job);
                        }}
                        className="w-full mt-2 inline-flex h-8 items-center justify-center gap-1.5 rounded bg-accent-terracotta-subtle border border-accent-terracotta-border text-accent-terracotta text-xs font-bold hover:bg-accent-terracotta-subtle/80 transition-colors"
                      >
                        <Zap className="size-3" />
                        <span>Pre-empt</span>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
