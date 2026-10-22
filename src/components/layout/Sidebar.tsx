"use client";
import React from "react";
import {
  LayoutGrid,
  Activity,
  CalendarClock,
  Wrench,
  Users,
  CircleDollarSign,
  ScrollText,
  SlidersHorizontal,
  X,
} from "lucide-react";

export type NavView =
  | "overview"
  | "machines"
  | "schedule"
  | "jobs"
  | "technicians"
  | "cost"
  | "logs"
  | "engine";

interface SidebarProps {
  currentView: NavView;
  onViewChange: (view: NavView) => void;
  criticalCount: number;
  activeJobsCount?: number;
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onViewChange,
  criticalCount,
  activeJobsCount = 2,
  mobileOpen = false,
  onCloseMobile,
}) => {
  const navItems = [
    {
      id: "overview" as NavView,
      label: "Overview",
      icon: LayoutGrid,
    },
    {
      id: "machines" as NavView,
      label: "Machines",
      icon: Activity,
      badge: criticalCount > 0 ? criticalCount : null,
      badgeColor: "critical",
    },
    {
      id: "schedule" as NavView,
      label: "Schedule (Gantt)",
      icon: CalendarClock,
    },
    {
      id: "jobs" as NavView,
      label: "Maintenance Jobs",
      icon: Wrench,
      badge: activeJobsCount > 0 ? activeJobsCount : null,
      badgeColor: "accent",
    },
    {
      id: "technicians" as NavView,
      label: "Technicians",
      icon: Users,
    },
    {
      id: "cost" as NavView,
      label: "Cost Analysis",
      icon: CircleDollarSign,
    },
    {
      id: "logs" as NavView,
      label: "Event Log",
      icon: ScrollText,
    },
    {
      id: "engine" as NavView,
      label: "Decision Engine",
      icon: SlidersHorizontal,
      highlight: true,
    },
  ];

  const handleNavClick = (viewId: NavView) => {
    onViewChange(viewId);
    if (onCloseMobile) onCloseMobile();
  };

  const sidebarContent = (
    <div className="flex h-full w-[235px] xl:w-[250px] flex-col border-r border-sidebar-border bg-sidebar select-none">
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between border-b border-sidebar-border px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-[4px] bg-foreground text-background font-mono text-xs font-bold tracking-wider shadow-sm">
            FG
          </div>
          <div className="leading-tight">
            <span className="text-[15px] font-bold tracking-tight text-foreground block">
              ForgeGuard
            </span>
            <span className="text-[11px] font-semibold text-foreground-muted block tracking-wider uppercase">
              Operations
            </span>
          </div>
        </div>

        {/* Mobile Close Button */}
        {onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="flex size-8 items-center justify-center rounded border border-border-normal text-foreground-muted hover:text-foreground md:hidden"
            aria-label="Close navigation"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      {/* Navigation List */}
      <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 p-3">
        <div className="px-3 pb-2 pt-2 text-xs font-semibold tracking-wider uppercase text-foreground-muted">
          Platform
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => handleNavClick(item.id)}
              className={`group relative flex h-[42px] items-center gap-3 rounded-[4px] px-3.5 text-left text-[14px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-forest ${
                isActive
                  ? "bg-sidebar-active font-semibold text-foreground"
                  : "text-foreground-muted hover:bg-surface-hover hover:text-foreground font-medium"
              }`}
            >
              {isActive && (
                <span
                  className="absolute inset-y-2 left-0 w-[3px] rounded-r bg-accent-forest"
                  aria-hidden="true"
                />
              )}
              <Icon
                className={`size-[18px] shrink-0 transition-colors ${
                  isActive
                    ? "text-accent-forest"
                    : "text-foreground-muted group-hover:text-foreground"
                }`}
              />
              <span className="flex-1 truncate">{item.label}</span>
              {item.badge !== null && item.badge !== undefined && (
                <span
                  className={`inline-flex h-5 min-w-5 items-center justify-center rounded-[3px] px-1.5 font-mono text-xs font-semibold border ${
                    item.badgeColor === "critical"
                      ? "text-status-critical bg-status-critical-bg border-status-critical-border"
                      : "text-accent-terracotta bg-accent-terracotta-subtle border-accent-terracotta-border"
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Operational Pipeline Footer Card */}
      <div className="m-3 space-y-2.5 rounded-[4px] border border-border-normal bg-surface p-3.5 text-xs shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-xs uppercase font-semibold text-foreground-muted tracking-wider">
            Inference Pipeline
          </span>
          <span className="flex items-center gap-1.5 text-xs text-accent-forest font-semibold">
            <span className="size-2 rounded-full bg-accent-forest" />
            Live
          </span>
        </div>
        <div className="flex items-baseline justify-between text-xs pt-0.5">
          <span className="font-mono text-foreground font-semibold">fg-gbm v3.2</span>
          <span className="font-mono text-foreground-muted text-[11.5px]">AUC 0.94</span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sticky Sidebar */}
      <aside className="sticky top-0 hidden h-screen shrink-0 md:flex">
        {sidebarContent}
      </aside>

      {/* Mobile Collapsible Navigation Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden" role="dialog" aria-modal="true">
          <div
            className="fixed inset-0 bg-foreground/20 backdrop-blur-[2px] transition-opacity"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <div className="relative z-10 flex h-full">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};
