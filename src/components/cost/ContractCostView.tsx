"use client";
import React, { useState } from "react";
import {
  CircleDollarSign,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Clock,
  Layers,
  ArrowRight,
} from "lucide-react";
import { CostAnalysisResponse, CostAnalysisOption } from "@/types/api";
import { formatCurrency } from "@/lib/data-generator";

interface ContractCostViewProps {
  costAnalysis: CostAnalysisResponse;
}

export const ContractCostView: React.FC<ContractCostViewProps> = ({ costAnalysis }) => {
  const [selectedOptionId, setSelectedOptionId] = useState(costAnalysis.recommended_option_id);

  const selectedOption =
    costAnalysis.options.find((o) => o.option_id === selectedOptionId) ??
    costAnalysis.options[0];

  return (
    <div className="space-y-6">
      {/* Backend Recommendation & Strategic Rationale Card */}
      <div className="panel p-5 sm:p-6 bg-surface border-l-4 border-l-accent-forest border border-border-normal space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle pb-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="size-5 text-accent-forest" />
            <h2 className="text-[17px] font-bold text-foreground tracking-tight">
              Backend Economic Optimization Rationale
            </h2>
          </div>
          <span className="font-mono text-xs font-bold px-2.5 py-1 rounded bg-accent-forest-subtle border border-accent-forest-border text-accent-forest uppercase">
            Recommended Action: {costAnalysis.options.find((o) => o.option_id === costAnalysis.recommended_option_id)?.label}
          </span>
        </div>

        <p className="text-sm leading-relaxed text-foreground">
          {costAnalysis.explanation}
        </p>

        <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-foreground-muted pt-1">
          <span>Currency: <strong className="text-foreground">{costAnalysis.currency}</strong></span>
          <span>·</span>
          <span>Generated: <strong className="text-foreground">{new Date(costAnalysis.generated_at).toLocaleTimeString()}</strong></span>
          <span>·</span>
          <span>Model: <strong className="text-foreground">Expected Loss Matrix v2.1</strong></span>
        </div>
      </div>

      {/* 4 Comparative Cost Options Cards */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="eyebrow text-foreground-muted text-xs">
            Evaluated Decision Alternatives
          </h3>
          <span className="text-xs text-foreground-muted">
            Click any alternative to inspect detailed assumptions
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
          {costAnalysis.options.map((option) => {
            const isRecommended = option.option_id === costAnalysis.recommended_option_id;
            const isSelected = option.option_id === selectedOptionId;

            return (
              <div
                key={option.option_id}
                onClick={() => setSelectedOptionId(option.option_id)}
                className={`panel p-5 sm:p-6 rounded-lg cursor-pointer transition-all flex flex-col justify-between space-y-4 border ${
                  isSelected
                    ? "border-border-strong bg-surface-raised shadow-md"
                    : isRecommended
                    ? "border-accent-forest-border bg-surface"
                    : "border-border-normal bg-surface hover:bg-surface-hover"
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2 border-b border-border-subtle pb-2.5">
                    <span className="font-bold text-foreground text-sm">
                      {option.label}
                    </span>
                    {isRecommended && (
                      <span className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded bg-accent-forest text-white uppercase shrink-0">
                        Optimal
                      </span>
                    )}
                  </div>

                  {/* Total Cost figure */}
                  <div>
                    <span className="text-xs text-foreground-muted uppercase tracking-wider block font-semibold">
                      Total Estimated Cost
                    </span>
                    <span
                      className={`font-mono text-2xl sm:text-3xl font-bold block mt-1 ${
                        isRecommended ? "text-accent-forest" : option.total_estimated_cost && option.total_estimated_cost > 30000 ? "text-status-critical" : "text-foreground"
                      }`}
                    >
                      {option.total_estimated_cost !== null
                        ? formatCurrency(option.total_estimated_cost)
                        : "Not Available"}
                    </span>
                  </div>

                  {/* Component Breakdown */}
                  <div className="space-y-2 pt-2 border-t border-border-subtle text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-foreground-muted">Labor / Service:</span>
                      <span className="font-mono font-semibold text-foreground">
                        {option.maintenance_cost !== null ? formatCurrency(option.maintenance_cost) : "—"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-foreground-muted">Direct Downtime Loss:</span>
                      <span className="font-mono font-semibold text-foreground">
                        {option.downtime_cost !== null ? formatCurrency(option.downtime_cost) : "—"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-foreground-muted">Delay Risk Cost:</span>
                      <span className="font-mono font-semibold text-status-critical">
                        {option.delay_risk_cost !== null ? formatCurrency(option.delay_risk_cost) : "—"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-foreground-muted">Interruption Penalty:</span>
                      <span className="font-mono font-semibold text-accent-terracotta">
                        {option.interruption_cost !== null ? formatCurrency(option.interruption_cost) : "—"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Feasibility Tag */}
                <div className="pt-3 border-t border-border-subtle flex items-center justify-between text-xs">
                  <span className="text-foreground-muted">Status:</span>
                  <span
                    className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded border uppercase ${
                      option.feasible
                        ? "bg-accent-forest-subtle text-accent-forest border-accent-forest-border"
                        : "bg-status-critical-bg text-status-critical border-status-critical-border"
                    }`}
                  >
                    {option.feasible ? "Feasible" : "Infeasible"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected Option Deep-Dive: Assumptions & Economic Model Parameters */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Assumptions Card */}
        <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4">
          <div className="flex items-center justify-between border-b border-border-subtle pb-3">
            <span className="font-bold text-foreground text-base">
              Operational Assumptions: {selectedOption.label}
            </span>
            <span className="eyebrow text-xs text-foreground-muted">
              Model Sensitivity
            </span>
          </div>

          <ul className="space-y-2.5 text-xs sm:text-[13px] text-foreground leading-relaxed">
            {selectedOption.assumptions.map((assumption, idx) => (
              <li key={idx} className="flex items-start gap-2.5">
                <span className="size-1.5 rounded-full bg-accent-forest shrink-0 mt-2" />
                <span>{assumption}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Global Economic Ratios Dock */}
        <div className="panel p-5 sm:p-6 bg-surface border border-border-normal space-y-4">
          <div className="flex items-center justify-between border-b border-border-subtle pb-3">
            <span className="font-bold text-foreground text-base">
              Economic Engine Parameters
            </span>
            <span className="eyebrow text-xs text-foreground-muted">
              Standard Cost Rates
            </span>
          </div>

          <dl className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-foreground-muted">Inspection Dispatch Fixed Overhead:</dt>
              <dd className="font-mono font-bold text-foreground">
                ${costAnalysis.parameters.inspection_dispatch_fee} / service
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-foreground-muted">Diagnostic Review Overhead:</dt>
              <dd className="font-mono font-bold text-foreground">
                ${costAnalysis.parameters.alert_review_overhead} / alert
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-foreground-muted">Unscheduled Downtime Loss Rate:</dt>
              <dd className="font-mono font-bold text-status-critical">
                ${costAnalysis.parameters.hourly_downtime_cost} / line-hour
              </dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-foreground-muted">Loaded Technician Hourly Rate:</dt>
              <dd className="font-mono font-bold text-foreground">
                ${costAnalysis.parameters.technician_rate} / hour
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
};
