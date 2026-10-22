"use client";
import React from "react";
import {
  Users,
  Wrench,
  CheckCircle2,
  Clock,
  ShieldCheck,
  Award,
  Zap,
} from "lucide-react";
import { TechnicianContract, JobContract } from "@/types/api";

interface TechniciansViewProps {
  technicians: TechnicianContract[];
  jobs: JobContract[];
  onSelectJob: (job: JobContract) => void;
}

export const TechniciansView: React.FC<TechniciansViewProps> = ({
  technicians,
  jobs,
  onSelectJob,
}) => {
  const availableCount = technicians.filter((t) => t.status === "available").length;
  const onJobCount = technicians.filter((t) => t.status === "on_job").length;
  const assignedCount = technicians.filter((t) => t.status === "assigned").length;

  return (
    <div className="space-y-6">
      {/* Header Metric Summary Strip */}
      <div className="panel p-5 sm:p-6 bg-surface grid grid-cols-2 lg:grid-cols-4 gap-4 divide-y lg:divide-y-0 lg:divide-x divide-border-subtle border border-border-normal">
        <div className="sm:px-4">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Available Specialists
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-forest mt-1.5 block">
            {availableCount} of {technicians.length}
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Ready for dispatch
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Actively on Job
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-accent-terracotta mt-1.5 block">
            {onJobCount} crew
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            On shop floor work orders
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Assigned & Staged
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground mt-1.5 block">
            {assignedCount} crew
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            Scheduled for next window
          </span>
        </div>

        <div className="sm:px-6 pt-3 lg:pt-0">
          <span className="text-xs uppercase font-semibold text-foreground-muted block tracking-wider">
            Shift Completion Rate
          </span>
          <span className="font-mono text-2xl sm:text-3xl font-bold text-foreground mt-1.5 block">
            96.4%
          </span>
          <span className="text-xs text-foreground-muted mt-0.5 block">
            LOTO & QA compliant
          </span>
        </div>
      </div>

      {/* Technician Roster Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {technicians.map((tech) => {
          const currentJob = jobs.find((j) => j.job_id === tech.current_job_id);

          return (
            <div
              key={tech.technician_id}
              className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4 flex flex-col justify-between"
            >
              <div className="space-y-3">
                {/* Header */}
                <div className="flex items-start justify-between gap-3 border-b border-border-subtle pb-3.5">
                  <div>
                    <h3 className="font-bold text-foreground text-base">
                      {tech.name}
                    </h3>
                    <p className="text-xs text-foreground-muted mt-0.5">
                      {tech.role}
                    </p>
                    <span className="font-mono text-[11px] text-foreground-muted mt-0.5 block">
                      {tech.technician_id} · {tech.shift}
                    </span>
                  </div>

                  <span
                    className={`inline-flex items-center gap-1.5 font-mono text-xs font-bold px-2.5 py-1 rounded border uppercase ${
                      tech.status === "available"
                        ? "bg-accent-forest-subtle text-accent-forest border-accent-forest-border"
                        : tech.status === "on_job"
                        ? "bg-accent-terracotta-subtle text-accent-terracotta border-accent-terracotta-border"
                        : "bg-surface-subtle text-foreground-muted border-border-normal"
                    }`}
                  >
                    <span
                      className={`size-2 rounded-full ${
                        tech.status === "available"
                          ? "bg-accent-forest"
                          : tech.status === "on_job"
                          ? "bg-accent-terracotta"
                          : "bg-status-warning"
                      }`}
                    />
                    {tech.status.replace("_", " ")}
                  </span>
                </div>

                {/* Current Assignment Card */}
                {currentJob ? (
                  <div
                    onClick={() => onSelectJob(currentJob)}
                    className="rounded-md border border-border-normal bg-surface-subtle p-3 space-y-1.5 cursor-pointer hover:border-border-strong transition-colors"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold uppercase tracking-wider text-foreground-muted text-[11px]">
                        Current Work Order
                      </span>
                      <span className="font-mono font-bold text-accent-terracotta">
                        {currentJob.job_id}
                      </span>
                    </div>
                    <p className="font-bold text-foreground text-xs leading-snug">
                      {currentJob.machine_name}
                    </p>
                    <div className="flex items-center justify-between text-xs text-foreground-muted font-mono pt-1">
                      <span>Progress: {currentJob.progress_percent}%</span>
                      <span>Avail in ~{currentJob.estimated_duration_minutes - currentJob.elapsed_minutes}m</span>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-border-normal p-3 text-xs text-foreground-muted text-center italic">
                    Standby on floor · Available for immediate dispatch
                  </div>
                )}

                {/* Skills tags */}
                <div className="space-y-1.5 pt-1">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-foreground-muted block">
                    Certified Competencies
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {tech.skills.map((s) => (
                      <span
                        key={s}
                        className="font-mono text-[11px] px-2 py-0.5 rounded bg-surface-subtle border border-border-subtle text-foreground"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Footer Metrics */}
              <div className="grid grid-cols-2 gap-2 pt-3 border-t border-border-subtle text-xs font-mono text-foreground-muted">
                <div>
                  <span className="text-[11px] block">Shift Orders:</span>
                  <span className="font-bold text-foreground">{tech.completed_jobs_count} closed</span>
                </div>
                <div>
                  <span className="text-[11px] block">Reliability:</span>
                  <span className="font-bold text-accent-forest">{(tech.efficiency_rating * 100).toFixed(0)}% QA Score</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
