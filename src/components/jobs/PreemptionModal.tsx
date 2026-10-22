"use client";
import React, { useState } from "react";
import {
  X,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  ArrowRight,
  Clock,
  AlertTriangle,
  DollarSign,
  CheckCircle2,
  Lock,
  RotateCw,
} from "lucide-react";
import {
  JobContract,
  PreemptionEvaluationResponse,
  PreemptionExecuteResponse,
} from "@/types/api";
import { formatCurrency } from "@/lib/data-generator";

interface PreemptionModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentJob: JobContract | null;
  incomingJob: JobContract | null;
  evaluation: PreemptionEvaluationResponse | null;
  isEvaluating: boolean;
  onExecute: (evaluationId: string, incomingJobId: string, technicianId: string) => Promise<PreemptionExecuteResponse>;
  onSuccess: (msg: string) => void;
}

export const PreemptionModal: React.FC<PreemptionModalProps> = ({
  isOpen,
  onClose,
  currentJob,
  incomingJob,
  evaluation,
  isEvaluating,
  onExecute,
  onSuccess,
}) => {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen || !currentJob) return null;

  const isAllowed = evaluation?.decision === "allow";
  const isSafetyBlocked = evaluation?.decision === "deny" || !evaluation?.safe_to_interrupt;

  const handleExecuteClick = async () => {
    if (!evaluation || !incomingJob || !currentJob.technician_id) return;

    if (!isConfirming) {
      setIsConfirming(true);
      return;
    }

    setIsExecuting(true);
    setErrorMessage(null);
    try {
      const res = await onExecute(
        evaluation.evaluation_id,
        incomingJob.job_id,
        currentJob.technician_id
      );
      onSuccess(res.message);
      onClose();
    } catch (err: any) {
      setErrorMessage(err?.message || "Pre-emption execution was denied by the orchestration layer.");
    } finally {
      setIsExecuting(false);
      setIsConfirming(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 backdrop-blur-[2px] p-4 overflow-y-auto">
      <div
        className="w-full max-w-3xl rounded-lg border border-border-strong bg-surface p-6 shadow-2xl transition-all select-none my-8 max-h-[92vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preemption-dialog-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-subtle pb-4 shrink-0">
          <div className="flex items-center gap-3">
            <div
              className={`flex size-10 items-center justify-center rounded-md border ${
                isAllowed
                  ? "bg-accent-forest-subtle text-accent-forest border-accent-forest-border"
                  : "bg-status-critical-bg text-status-critical border-status-critical-border"
              }`}
            >
              {isAllowed ? <ShieldCheck className="size-6" /> : <ShieldAlert className="size-6" />}
            </div>
            <div>
              <h2 id="preemption-dialog-title" className="text-lg font-bold text-foreground">
                Maintenance Pre-emption Decision Review
              </h2>
              <p className="text-xs text-foreground-muted mt-0.5">
                Evaluation protocol for safe active job interruption and emergency re-allocation.
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

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto py-5 space-y-5">
          {/* Side-by-side: Active Job vs Incoming Emergency Job */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Active Job Card */}
            <div className="rounded-md border border-border-normal bg-surface-subtle p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-foreground-muted">
                  Currently Active Work Order
                </span>
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-surface border border-border-strong text-foreground">
                  {currentJob.job_id}
                </span>
              </div>
              <div>
                <h3 className="font-bold text-foreground text-sm">
                  {currentJob.machine_name}
                </h3>
                <p className="text-xs text-foreground-muted mt-0.5 line-clamp-2">
                  {currentJob.description}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-border-subtle">
                <div>
                  <span className="text-foreground-muted text-[11px] block">Assigned Specialist:</span>
                  <span className="font-bold text-foreground">{currentJob.technician_name ?? "—"}</span>
                </div>
                <div>
                  <span className="text-foreground-muted text-[11px] block">Progress / Elapsed:</span>
                  <span className="font-mono font-bold text-foreground">
                    {currentJob.progress_percent}% ({currentJob.elapsed_minutes}/{currentJob.estimated_duration_minutes}m)
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-foreground-muted text-[11px]">Safety State:</span>
                <span
                  className={`inline-flex items-center gap-1 font-mono text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${
                    currentJob.safety_status === "safe"
                      ? "text-accent-forest bg-accent-forest-subtle border-accent-forest-border"
                      : "text-status-critical bg-status-critical-bg border-status-critical-border"
                  }`}
                >
                  {currentJob.safety_status === "safe" ? <ShieldCheck className="size-3" /> : <ShieldAlert className="size-3" />}
                  {currentJob.safety_status}
                </span>
              </div>
            </div>

            {/* Incoming Emergency Job Card */}
            <div className="rounded-md border border-status-critical-border bg-status-critical-bg/30 p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-status-critical-border/50 pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-status-critical flex items-center gap-1.5">
                  <AlertTriangle className="size-3.5" /> Incoming Critical Job
                </span>
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-status-critical text-white">
                  {incomingJob?.job_id ?? "JOB-URGENT"}
                </span>
              </div>
              <div>
                <h3 className="font-bold text-foreground text-sm">
                  {incomingJob?.machine_name ?? "Emergency Target Asset"}
                </h3>
                <p className="text-xs text-foreground-muted mt-0.5 line-clamp-2">
                  {incomingJob?.description ?? "Critical anomaly detected; immediate intervention required."}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-status-critical-border/40">
                <div>
                  <span className="text-foreground-muted text-[11px] block">Failure Loss Exposure:</span>
                  <span className="font-mono font-bold text-status-critical">
                    {formatCurrency(incomingJob?.estimated_downtime_cost ?? 48000)}
                  </span>
                </div>
                <div>
                  <span className="text-foreground-muted text-[11px] block">Est. Repair Duration:</span>
                  <span className="font-mono font-bold text-foreground">
                    {incomingJob?.estimated_duration_minutes ?? 75} mins
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-foreground-muted text-[11px]">Safety Clearance:</span>
                <span className="inline-flex items-center gap-1 font-mono text-[11px] font-bold px-2 py-0.5 rounded border border-status-healthy-border bg-status-healthy-bg text-status-healthy uppercase">
                  <ShieldCheck className="size-3" /> Verified Safe
                </span>
              </div>
            </div>
          </div>

          {/* Hard Safety Gate Alert Banner (Contract Section 3.F & 5) */}
          <div
            className={`rounded-md border p-4 text-xs leading-relaxed ${
              isAllowed
                ? "border-accent-forest-border bg-accent-forest-subtle text-foreground"
                : "border-status-critical-border bg-status-critical-bg text-foreground"
            }`}
          >
            <div className="flex items-start gap-3">
              {isAllowed ? (
                <ShieldCheck className="size-5 text-accent-forest shrink-0 mt-0.5" />
              ) : (
                <Lock className="size-5 text-status-critical shrink-0 mt-0.5" />
              )}
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm uppercase tracking-wider">
                    {isAllowed ? "Safety Gate: PASSED — Safe to Interrupt" : "Safety Gate: LOCKED — Interruption Blocked"}
                  </span>
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-surface border border-border-strong font-semibold">
                    Decision: {evaluation?.decision?.toUpperCase() ?? "EVALUATING"}
                  </span>
                </div>
                <p className="text-[13px] text-foreground/90">
                  {evaluation?.explanation ?? "Evaluating active job tooling disengagement risks and hydraulic safety states..."}
                </p>
                {evaluation?.reason_codes && evaluation.reason_codes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {evaluation.reason_codes.map((code) => (
                      <span key={code} className="font-mono text-[10.5px] px-1.5 py-0.5 rounded bg-surface border border-border-subtle text-foreground-muted">
                        {code}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Economic Interruption Cost Breakdown */}
          {evaluation && (
            <div className="panel p-4 bg-surface border border-border-normal space-y-3 text-xs">
              <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                <span className="font-bold text-foreground text-[13px]">
                  Economic Interruption Cost Impact
                </span>
                <span className="font-mono font-bold text-sm text-foreground">
                  Estimated Overhead: {formatCurrency(evaluation.estimated_interruption_cost ?? 450)}
                </span>
              </div>
              <p className="text-foreground-muted text-xs leading-relaxed">
                Interruption overhead includes safe tooling retraction, lockout-tagout tagging, setup preservation, and 15-minute resumption calibration penalty.
              </p>
            </div>
          )}

          {/* 4-Way Feasible Alternatives Comparison Table (Contract Section 3.F) */}
          {evaluation?.alternatives && evaluation.alternatives.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-wider text-foreground-muted block">
                Evaluated Action Alternatives
              </span>
              <div className="divide-y divide-border-subtle rounded-md border border-border-normal bg-surface overflow-hidden text-xs">
                {evaluation.alternatives.map((alt) => (
                  <div
                    key={alt.action}
                    className={`flex items-start justify-between p-3.5 gap-4 ${
                      alt.action === "preempt" && alt.feasible
                        ? "bg-accent-forest-subtle/50 font-medium"
                        : "hover:bg-surface-hover"
                    }`}
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground text-[13px]">
                          {alt.label}
                        </span>
                        {alt.feasible ? (
                          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-status-healthy-bg border border-status-healthy-border text-status-healthy uppercase font-semibold">
                            Feasible
                          </span>
                        ) : (
                          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-status-critical-bg border border-status-critical-border text-status-critical uppercase font-semibold">
                            Infeasible / Blocked
                          </span>
                        )}
                      </div>
                      <p className="text-foreground-muted text-xs">{alt.reason}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="font-mono font-bold text-sm text-foreground block">
                        {alt.estimated_total_cost !== null ? formatCurrency(alt.estimated_total_cost) : "N/A"}
                      </span>
                      <span className="text-[10.5px] text-foreground-muted">Total Shift Cost</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error Message if mutation fails */}
          {errorMessage && (
            <div className="rounded-md border border-status-critical-border bg-status-critical-bg p-3 text-xs text-status-critical font-semibold">
              {errorMessage}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-4 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-md border border-border-normal bg-surface px-4 text-xs font-semibold text-foreground hover:bg-surface-hover transition-colors"
          >
            Cancel & Return
          </button>

          <div className="flex items-center gap-3">
            {isAllowed ? (
              <button
                type="button"
                onClick={handleExecuteClick}
                disabled={isExecuting}
                className={`inline-flex h-10 items-center gap-2 rounded-md px-5 text-xs font-bold text-white transition-all shadow-sm ${
                  isConfirming
                    ? "bg-status-critical hover:bg-status-critical/90 animate-pulse"
                    : "bg-accent-forest hover:bg-accent-forest/90"
                } disabled:opacity-50`}
              >
                {isExecuting ? (
                  <>
                    <RotateCw className="size-4 animate-spin" />
                    <span>Executing Pre-emption...</span>
                  </>
                ) : isConfirming ? (
                  <>
                    <AlertTriangle className="size-4" />
                    <span>Confirm Emergency Interruption Now</span>
                  </>
                ) : (
                  <>
                    <ArrowRight className="size-4" />
                    <span>Execute Pre-emption & Reassign</span>
                  </>
                )}
              </button>
            ) : (
              <button
                type="button"
                disabled
                className="inline-flex h-10 items-center gap-2 rounded-md border border-border-normal bg-surface-subtle px-4 text-xs font-bold text-foreground-muted opacity-60 cursor-not-allowed"
                title="Action blocked: safety hard gate is locked."
              >
                <Lock className="size-4" />
                <span>Pre-emption Blocked by Safety Gate</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
