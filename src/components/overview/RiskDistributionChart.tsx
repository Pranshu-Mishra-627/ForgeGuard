"use client";
import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { Machine, RiskLevel } from "@/lib/types";

interface RiskDistributionChartProps {
  machines: Machine[];
  selectedRisk: RiskLevel | "all";
  onSelectRisk: (risk: RiskLevel | "all") => void;
  className?: string;
}

export const RiskDistributionChart: React.FC<RiskDistributionChartProps> = ({
  machines,
  selectedRisk,
  onSelectRisk,
  className = "",
}) => {
  const counts = {
    critical: machines.filter((m) => m.risk === "critical").length,
    high: machines.filter((m) => m.risk === "high").length,
    medium: machines.filter((m) => m.risk === "medium").length,
    low: machines.filter((m) => m.risk === "low").length,
  };

  const chartData = [
    { bracket: "0–20% Low", risk: "low", count: counts.low, color: "#9E9E94" },
    { bracket: "20–45% Med", risk: "medium", count: counts.medium, color: "#526B57" },
    { bracket: "45–70% High", risk: "high", count: counts.high, color: "#C98A2C" },
    { bracket: "70–100% Crit", risk: "critical", count: counts.critical, color: "#B84A39" },
  ];

  const handleToggle = (risk: RiskLevel) => {
    onSelectRisk(selectedRisk === risk ? "all" : risk);
  };

  return (
    <section className={`panel flex flex-col overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-normal px-6 py-4.5">
        <div>
          <h2 className="text-[18px] font-bold tracking-tight text-foreground">
            Risk Distribution
          </h2>
          <p className="mt-1 text-[13px] text-foreground-muted">
            Monitored machines by probability bracket · click to filter
          </p>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex flex-wrap gap-2 px-6 pt-3.5" role="group" aria-label="Filter by risk level">
        {(["critical", "high", "medium", "low"] as RiskLevel[]).map((r) => {
          const isActive = selectedRisk === r;
          const dotColor =
            r === "critical"
              ? "bg-status-critical"
              : r === "high"
              ? "bg-status-warning"
              : r === "medium"
              ? "bg-accent-forest"
              : "bg-foreground-muted";

          return (
            <button
              key={r}
              type="button"
              aria-pressed={isActive}
              onClick={() => handleToggle(r)}
              className={`flex items-center gap-2 rounded-[4px] border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-forest ${
                isActive
                  ? "bg-surface-raised font-bold text-foreground border-border-strong shadow-sm"
                  : "bg-surface text-foreground-muted hover:bg-surface-hover hover:text-foreground border-border-normal font-medium"
              }`}
            >
              <span className={`size-2 rounded-full ${dotColor}`} aria-hidden="true" />
              <span className="capitalize">{r}</span>
              <span className="font-mono text-foreground font-bold">{counts[r]}</span>
            </button>
          );
        })}
      </div>

      {/* Chart */}
      <div className="flex-1 px-4 pb-4 pt-3">
        <div className="h-[270px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 16, right: 16, left: -16, bottom: 6 }}
            >
              <CartesianGrid
                strokeDasharray="2 2"
                stroke="#E6E1D8"
                vertical={false}
              />
              <XAxis
                dataKey="bracket"
                stroke="#77786F"
                fontSize={12}
                tickLine={false}
                axisLine={{ stroke: "#E6E1D8" }}
              />
              <YAxis
                stroke="#77786F"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    return (
                      <div className="rounded-[4px] border border-border-normal bg-surface px-3.5 py-2 text-sm shadow-md">
                        <div className="font-bold text-foreground">{data.bracket}</div>
                        <div className="mt-1 text-foreground-muted">
                          Count:{" "}
                          <span className="font-mono font-bold text-foreground">
                            {data.count} units
                          </span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.color}
                    opacity={
                      selectedRisk === "all" || selectedRisk === entry.risk
                        ? 1
                        : 0.35
                    }
                    className="cursor-pointer transition-opacity"
                    onClick={() => handleToggle(entry.risk as RiskLevel)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
};
