"use client";
import React, { useState } from "react";
import {
  CalendarClock,
  RotateCw,
  Sliders,
  ListFilter,
  Columns,
  Table,
  Wrench,
  AlertCircle,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { ScheduleAssignment, TechnicianContract, JobContract, ReplanRequest } from "@/types/api";

interface ScheduleGanttViewProps {
  assignments: ScheduleAssignment[];
  technicians: TechnicianContract[];
  unassignedJobIds: string[];
  jobs: JobContract[];
  onReplan: (req: ReplanRequest) => Promise<void>;
  onSelectJob: (job: JobContract) => void;
  isReplanning?: boolean;
}

export const ScheduleGanttView: React.FC<ScheduleGanttViewProps> = ({
  assignments,
  technicians,
  unassignedJobIds,
  jobs,
  onReplan,
  onSelectJob,
  isReplanning = false,
}) => {
  const [viewMode, setViewMode] = useState<"gantt" | "table">("gantt");
  const [replanReason, setReplanReason] = useState<ReplanRequest["reason"]>("new_critical_job");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Time ticks across 8-hour shift (08:00 to 16:00)
  const timeHours = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"];

  const handleReplanClick = async (reason: ReplanRequest["reason"]) => {
    setIsDropdownOpen(false);
    await onReplan({ reason });
  };

  const getJobForAssignment = (jobId: string) => jobs.find((j) => j.job_id === jobId);

  return (
    <div className="space-y-6">
      {/* Header & Controls Bar */}
      <div className="panel p-5 sm:p-6 bg-surface border border-border-normal flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <CalendarClock className="size-5 text-accent-forest" />
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Maintenance Shift Schedule & Gantt Timeline
            </h2>
          </div>
          <p className="text-[13px] text-foreground-muted mt-0.5">
            Deterministic allocation of technician work orders across the 8-hour operational shift envelope.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Gantt vs Table Toggle */}
          <div className="inline-flex rounded-md border border-border-normal bg-surface p-1 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("gantt")}
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
                viewMode === "gantt"
                  ? "bg-surface-raised text-foreground shadow-sm font-bold"
                  : "text-foreground-muted hover:text-foreground"
              }`}
            >
              <Columns className="size-3.5" />
              <span>Gantt Timeline</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
                viewMode === "table"
                  ? "bg-surface-raised text-foreground shadow-sm font-bold"
                  : "text-foreground-muted hover:text-foreground"
              }`}
            >
              <Table className="size-3.5" />
              <span>Roster List</span>
            </button>
          </div>

          {/* Replan Button with reason prompt */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsDropdownOpen((v) => !v)}
              disabled={isReplanning}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-accent-forest-border bg-accent-forest text-white px-4 text-xs font-bold hover:bg-accent-forest/90 transition-all shadow-sm disabled:opacity-50"
            >
              <RotateCw className={`size-3.5 ${isReplanning ? "animate-spin" : ""}`} />
              <span>{isReplanning ? "Recalculating..." : "Recalculate Schedule"}</span>
            </button>

            {isDropdownOpen && (
              <div className="absolute right-0 top-12 z-20 w-64 rounded-md border border-border-strong bg-surface p-2 shadow-xl space-y-1 text-xs">
                <div className="px-2.5 py-1 text-[11px] font-bold uppercase text-foreground-muted tracking-wider">
                  Select Replan Trigger
                </div>
                {[
                  { id: "new_critical_job", label: "New Critical Anomaly Arrived" },
                  { id: "technician_unavailable", label: "Technician Roster Absence" },
                  { id: "end_of_shift_rebalance", label: "Mid-Shift Workload Rebalance" },
                  { id: "operator_override", label: "Supervisor Override Directives" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleReplanClick(item.id as any)}
                    className="w-full text-left rounded px-2.5 py-2 font-medium text-foreground hover:bg-surface-hover hover:text-accent-forest transition-colors"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Unassigned Jobs Shelf */}
      {unassignedJobIds.length > 0 && (
        <div className="rounded-md border border-status-warning-border bg-status-warning-bg p-4 flex items-start justify-between gap-4 text-xs">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="size-5 text-status-warning shrink-0" />
            <div>
              <span className="font-bold text-foreground text-[13px]">
                {unassignedJobIds.length} Unassigned Work Orders Pending Technician Slots
              </span>
              <p className="text-foreground-muted mt-0.5">
                These work orders are queued in the buffer. Click &quot;Recalculate Schedule&quot; or reassign technicians to allocate shift time.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            {unassignedJobIds.map((id) => (
              <span key={id} className="font-mono text-xs font-bold px-2.5 py-1 rounded bg-surface border border-status-warning-border text-foreground">
                {id}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Main View: Gantt vs Table */}
      {viewMode === "gantt" ? (
        <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4 overflow-x-auto">
          {/* Timeline Header Bar */}
          <div className="min-w-[800px]">
            <div className="grid grid-cols-12 border-b border-border-normal pb-3 text-xs font-mono font-semibold text-foreground-muted">
              <div className="col-span-3 text-foreground font-sans font-bold uppercase tracking-wider text-xs">
                Technician Resource
              </div>
              <div className="col-span-9 grid grid-cols-8 text-center">
                {timeHours.slice(0, 8).map((hour, idx) => (
                  <span key={hour} className="border-l border-border-subtle pl-1 text-[11.5px]">
                    {hour}
                  </span>
                ))}
              </div>
            </div>

            {/* Swimlanes for Each Technician */}
            <div className="divide-y divide-border-subtle pt-2">
              {technicians.map((tech) => {
                const techAssignments = assignments.filter((a) => a.technician_id === tech.technician_id);

                return (
                  <div key={tech.technician_id} className="grid grid-cols-12 py-3.5 items-center gap-2 hover:bg-surface-hover/50 rounded transition-colors">
                    {/* Technician Info Column */}
                    <div className="col-span-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground text-sm">
                          {tech.name}
                        </span>
                        <span
                          className={`size-2 rounded-full ${
                            tech.status === "on_job"
                              ? "bg-accent-terracotta"
                              : tech.status === "available"
                              ? "bg-accent-forest"
                              : "bg-status-warning"
                          }`}
                        />
                      </div>
                      <span className="text-xs text-foreground-muted block mt-0.5">
                        {tech.role}
                      </span>
                      <span className="font-mono text-[11px] text-foreground-muted block">
                        {tech.technician_id} · {tech.shift.split(" ")[0]}
                      </span>
                    </div>

                    {/* Timeline Block Track (9 cols) */}
                    <div className="col-span-9 relative h-12 bg-surface-subtle border border-border-subtle rounded-md flex items-center px-2">
                      {/* Hour divider grid lines */}
                      <div className="absolute inset-0 grid grid-cols-8 pointer-events-none opacity-40">
                        {Array.from({ length: 8 }).map((_, i) => (
                          <div key={i} className="border-r border-border-subtle h-full" />
                        ))}
                      </div>

                      {/* Job Blocks */}
                      {techAssignments.length === 0 ? (
                        <span className="text-xs text-foreground-muted italic z-10 pl-2">
                          Available for dispatch assignment
                        </span>
                      ) : (
                        techAssignments.map((assignment, aIdx) => {
                          const jobObj = getJobForAssignment(assignment.job_id);

                          const isCrit = assignment.priority === "critical";
                          const isHigh = assignment.priority === "high";

                          return (
                            <button
                              key={assignment.job_id}
                              type="button"
                              onClick={() => jobObj && onSelectJob(jobObj)}
                              style={{
                                width: `${Math.min(100, Math.max(30, (jobObj?.estimated_duration_minutes ?? 60) * 1.2))}%`,
                                marginLeft: `${aIdx * 20}%`,
                              }}
                              className={`z-10 group relative flex flex-col justify-center h-10 px-3 rounded text-left transition-all shadow-sm cursor-pointer border ${
                                isCrit
                                  ? "bg-status-critical text-white border-status-critical-border hover:bg-status-critical/90"
                                  : isHigh
                                  ? "bg-status-warning-bg text-foreground border-status-warning-border hover:border-border-strong"
                                  : "bg-surface text-foreground border-border-strong hover:bg-surface-raised"
                              }`}
                              title={`Click to inspect ${assignment.job_id}`}
                            >
                              <div className="flex items-center justify-between text-xs font-mono font-bold leading-tight">
                                <span>{assignment.job_id}</span>
                                <span>{assignment.machine_id}</span>
                              </div>
                              <span className="text-[11px] truncate opacity-90 block">
                                {jobObj?.description?.split(" ")[0]} {jobObj?.description?.split(" ")[1] ?? "Maintenance"}
                              </span>
                            </button>
                          );
                        })
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Accessible Table List View */
        <div className="panel overflow-hidden bg-surface border border-border-normal">
          <table className="w-full text-left text-sm border-collapse">
            <thead className="bg-surface-subtle border-b border-border-normal eyebrow h-11 text-foreground-muted">
              <tr>
                <th className="px-5 font-bold">Job ID</th>
                <th className="px-4 font-bold">Target Machine</th>
                <th className="px-4 font-bold">Assigned Specialist</th>
                <th className="px-4 font-bold">Priority</th>
                <th className="px-4 font-bold">Planned Window</th>
                <th className="px-4 font-bold">Status</th>
                <th className="px-5 font-bold">Scheduling Rationale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle bg-surface">
              {assignments.map((a) => {
                const jobObj = getJobForAssignment(a.job_id);
                return (
                  <tr
                    key={a.job_id}
                    onClick={() => jobObj && onSelectJob(jobObj)}
                    className="hover:bg-surface-hover cursor-pointer transition-colors"
                  >
                    <td className="px-5 py-3.5 font-mono font-bold text-foreground">
                      {a.job_id}
                    </td>
                    <td className="px-4 py-3.5 font-mono font-semibold text-foreground">
                      {a.machine_id}
                    </td>
                    <td className="px-4 py-3.5 font-medium text-foreground">
                      {a.technician_name ?? a.technician_id}
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`font-mono text-xs font-bold uppercase px-2 py-0.5 rounded border ${
                          a.priority === "critical"
                            ? "bg-status-critical-bg text-status-critical border-status-critical-border"
                            : a.priority === "high"
                            ? "bg-status-warning-bg text-status-warning border-status-warning-border"
                            : "bg-surface-subtle text-foreground-muted border-border-normal"
                        }`}
                      >
                        {a.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs text-foreground-muted">
                      {new Date(a.planned_start_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      {" – "}
                      {new Date(a.planned_end_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs font-bold capitalize">
                      {a.status.replace("_", " ")}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-foreground-muted max-w-xs truncate">
                      {a.reason ?? "Cost-weighted priority rank"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
