"use client";
import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from "recharts";
import { Target } from "lucide-react";
import { ThresholdCostPoint } from "@/lib/types";
import { formatCurrency } from "@/lib/data-generator";

interface CostAnalysisChartProps {
  slots: number;
  costCurve: ThresholdCostPoint[];
  selectedThreshold: number;
  onThresholdChange: (t: number) => void;
  optimalPoint: ThresholdCostPoint;
  className?: string;
  chartHeight?: number;
}

export const CostAnalysisChart: React.FC<CostAnalysisChartProps> = ({
  slots,
  costCurve,
  selectedThreshold,
  onThresholdChange,
  optimalPoint,
  className = "",
  chartHeight = 280,
}) => {
  const currentPoint =
    costCurve.find((p) => Math.abs(p.threshold - selectedThreshold) < 0.001) ??
    costCurve[0];

  const diffVsOptimal = currentPoint.cost - optimalPoint.cost;
  const isOptimal = Math.abs(diffVsOptimal) < 1;

  // Format data for chart
  const formattedData = costCurve.map((p) => ({
    ...p,
    thresholdPct: `${Math.round(p.threshold * 100)}%`,
    totalCostK: Math.round(p.cost / 1000),
    failureCostK: Math.round(p.failureCost / 1000),
    maintenanceCostK: Math.round(p.maintenanceCost / 1000),
  }));

  return (
    <section className={`panel flex flex-col overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-normal px-5 py-4 sm:px-6">
        <div>
          <h2 className="text-[17px] font-bold tracking-tight text-foreground">
            Alert Threshold vs. Expected Cost
          </h2>
          <p className="mt-0.5 text-[13px] text-foreground-muted">
            Expected shift cost model with {slots} technician slots · inspection $1.8k, alert review $260
          </p>
        </div>

        <button
          type="button"
          onClick={() => onThresholdChange(optimalPoint.threshold)}
          disabled={isOptimal}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-border-normal bg-surface px-3.5 text-xs font-semibold text-foreground transition-colors hover:bg-surface-hover hover:border-border-strong disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent-forest shadow-[0_1px_2px_rgba(37,41,35,0.04)]"
        >
          <Target className="size-4 text-accent-forest" />
          <span>Set Optimal ({Math.round(optimalPoint.threshold * 100)}%)</span>
        </button>
      </div>

      {/* KPI Comparison Metrics */}
      <dl className="grid grid-cols-3 divide-x divide-border-subtle border-b border-border-normal bg-surface-subtle">
        <div className="px-5 py-3 sm:px-6">
          <dt className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">Current Threshold</dt>
          <dd className="mt-1 font-mono text-base sm:text-lg font-bold tabular-nums text-foreground">
            {Math.round(selectedThreshold * 100)}%
          </dd>
        </div>
        <div className="px-5 py-3 sm:px-6">
          <dt className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">Total Expected Cost</dt>
          <dd className="mt-1 font-mono text-base sm:text-lg font-bold tabular-nums text-foreground">
            {formatCurrency(currentPoint.cost)}
          </dd>
        </div>
        <div className="px-5 py-3 sm:px-6">
          <dt className="text-xs font-semibold uppercase tracking-wider text-foreground-muted">
            Delta vs. Cost Minimum
          </dt>
          <dd
            className={`mt-1 font-mono text-base sm:text-lg font-bold tabular-nums ${
              isOptimal ? "text-accent-forest" : "text-status-warning"
            }`}
          >
            {isOptimal ? "Optimal Minimum" : `+${formatCurrency(diffVsOptimal)}`}
          </dd>
        </div>
      </dl>

      {/* Recharts Curve */}
      <div className="flex-1 px-4 pt-4 sm:px-6">
        <div style={{ height: chartHeight }} className="w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={formattedData}
              margin={{ top: 12, right: 16, left: -6, bottom: 4 }}
            >
              <CartesianGrid
                strokeDasharray="2 2"
                stroke="#E5E2DC"
                vertical={false}
              />
              <XAxis
                dataKey="thresholdPct"
                stroke="#74766F"
                fontSize={12}
                tickLine={false}
                axisLine={{ stroke: "#E5E2DC" }}
              />
              <YAxis
                stroke="#74766F"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${v}k`}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload as ThresholdCostPoint & {
                      thresholdPct: string;
                    };
                    return (
                      <div className="rounded-md border border-border-normal bg-surface px-4 py-3 text-sm shadow-md">
                        <div className="font-bold text-foreground">
                          Threshold: {data.thresholdPct}
                        </div>
                        <div className="mt-1.5 space-y-1 text-xs sm:text-[13px] text-foreground-muted">
                          <div>
                            Total Cost:{" "}
                            <span className="font-mono font-bold text-foreground">
                              {formatCurrency(data.cost)}
                            </span>
                          </div>
                          <div>
                            Failure Exposure:{" "}
                            <span className="font-mono font-bold text-status-critical">
                              {formatCurrency(data.failureCost)}
                            </span>
                          </div>
                          <div>
                            Dispatch & Review:{" "}
                            <span className="font-mono font-bold text-accent-terracotta">
                              {formatCurrency(data.maintenanceCost)}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              {/* Selected threshold reference line */}
              <ReferenceLine
                x={`${Math.round(selectedThreshold * 100)}%`}
                stroke="#252923"
                strokeDasharray="3 3"
                strokeWidth={1.5}
              />
              {/* Optimal reference dot */}
              <ReferenceDot
                x={`${Math.round(optimalPoint.threshold * 100)}%`}
                y={Math.round(optimalPoint.cost / 1000)}
                r={5}
                fill="#536B56"
                stroke="#FFFFFF"
                strokeWidth={2}
              />
              {/* Total cost curve */}
              <Line
                type="monotone"
                dataKey="totalCostK"
                name="Total cost"
                stroke="#252923"
                strokeWidth={2.2}
                dot={false}
              />
              {/* Failure exposure curve */}
              <Line
                type="monotone"
                dataKey="failureCostK"
                name="Failure exposure"
                stroke="#B64A38"
                strokeWidth={1.8}
                strokeDasharray="3 3"
                dot={false}
              />
              {/* Maintenance cost curve */}
              <Line
                type="monotone"
                dataKey="maintenanceCostK"
                name="Maintenance cost"
                stroke="#B97857"
                strokeWidth={1.8}
                strokeDasharray="3 3"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border-subtle bg-surface-subtle px-5 py-3 sm:px-6 text-xs text-foreground-muted">
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-3.5 rounded-full bg-foreground" aria-hidden="true" />
          Total expected cost
        </span>
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-3.5 rounded-full bg-status-critical" aria-hidden="true" />
          Failure risk exposure
        </span>
        <span className="flex items-center gap-2">
          <span className="h-0.5 w-3.5 rounded-full bg-accent-terracotta" aria-hidden="true" />
          Inspection + alert review
        </span>
        <span className="flex items-center gap-2">
          <span className="size-2.5 rounded-full bg-accent-forest" aria-hidden="true" />
          Optimal cost minimum
        </span>
      </div>

      {/* Threshold Slider Control */}
      <div className="flex items-center gap-4 px-5 py-3.5 sm:px-6 bg-surface">
        <span className="font-mono text-xs font-semibold text-foreground-muted">5%</span>
        <input
          type="range"
          min={0.05}
          max={0.95}
          step={0.05}
          value={selectedThreshold}
          onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
          aria-label="Alert threshold"
          className="h-2 w-full cursor-pointer appearance-none rounded bg-surface-subtle border border-border-normal accent-accent-forest focus-visible:outline-none"
        />
        <span className="font-mono text-xs font-semibold text-foreground-muted">95%</span>
      </div>
    </section>
  );
};
