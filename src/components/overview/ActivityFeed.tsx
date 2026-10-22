"use client";
import React from "react";
import { Cpu, AlertCircle, CalendarCheck, Activity } from "lucide-react";
import { DecisionLogEvent } from "@/lib/types";

interface ActivityFeedProps {
  events: DecisionLogEvent[];
  className?: string;
  listHeight?: string;
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({
  events,
  className = "",
  listHeight = "max-h-[460px]",
}) => {
  const getEventBadge = (kind: DecisionLogEvent["kind"]) => {
    switch (kind) {
      case "alert":
        return {
          icon: AlertCircle,
          textColor: "text-status-critical",
          bgColor: "bg-status-critical-bg border-status-critical-border",
        };
      case "schedule":
        return {
          icon: CalendarCheck,
          textColor: "text-accent-forest",
          bgColor: "bg-accent-forest-subtle border-accent-forest-border",
        };
      case "prediction":
        return {
          icon: Cpu,
          textColor: "text-foreground",
          bgColor: "bg-surface-subtle border-border-normal",
        };
      case "system":
      default:
        return {
          icon: Activity,
          textColor: "text-foreground-muted",
          bgColor: "bg-surface-subtle border-border-normal",
        };
    }
  };

  return (
    <section className={`panel flex flex-col overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-normal px-5 py-4 sm:px-6">
        <div>
          <h2 className="text-[17px] font-bold tracking-tight text-foreground">
            Pipeline Activity
          </h2>
          <p className="mt-0.5 text-[13px] text-foreground-muted">
            Inference, threshold alerts, and dispatch log
          </p>
        </div>
      </div>

      {/* Events List */}
      <ol className={`flex-1 overflow-auto divide-y divide-border-subtle p-0 bg-surface ${listHeight}`} aria-live="polite">
        {events.map((evt, idx) => {
          const badge = getEventBadge(evt.kind);
          const Icon = badge.icon;
          return (
            <li
              key={evt.id || idx}
              className="flex items-start gap-3.5 px-5 py-3.5 sm:px-6 transition-colors hover:bg-surface-hover"
            >
              <span
                className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border ${badge.bgColor} ${badge.textColor}`}
              >
                <Icon className="size-4" />
                <span className="sr-only">{evt.kind}</span>
              </span>

              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] leading-relaxed text-foreground">
                  {evt.message}
                </p>
                <p className="mt-1 font-mono text-xs tabular-nums text-foreground-muted">
                  {evt.time}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
};
