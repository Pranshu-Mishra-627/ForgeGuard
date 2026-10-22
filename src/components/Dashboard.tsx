"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { Sidebar, NavView } from "./layout/Sidebar";
import { TopHeader } from "./layout/TopHeader";
import { CriticalBanner } from "./overview/CriticalBanner";
import { KpiRow } from "./overview/KpiRow";
import { MachineRiskTable } from "./overview/MachineRiskTable";
import { TechnicianAllocation } from "./overview/TechnicianAllocation";
import { RiskDistributionChart } from "./overview/RiskDistributionChart";
import { CostAnalysisChart } from "./overview/CostAnalysisChart";
import { ActivityFeed } from "./overview/ActivityFeed";
import { MachineDetailDrawer } from "./machines/MachineDetailDrawer";
import { FleetView } from "./fleet/FleetView";
import { DecisionEngineView } from "./engine/DecisionEngineView";
import { SettingsView } from "./settings/SettingsView";

// Contract & Orchestration Components
import { SimulationControlBar } from "./simulation/SimulationControlBar";
import { InjectFailureModal } from "./simulation/InjectFailureModal";
import { PreemptionModal } from "./jobs/PreemptionModal";
import { JobsView } from "./jobs/JobsView";
import { ScheduleGanttView } from "./schedule/ScheduleGanttView";
import { TechniciansView } from "./technicians/TechniciansView";
import { ContractCostView } from "./cost/ContractCostView";
import { AuditLogView } from "./logs/AuditLogView";

// API Clients & Types
import { simulationApi } from "@/api/simulation";
import { machinesApi } from "@/api/machines";
import { jobsApi } from "@/api/jobs";
import { techniciansApi } from "@/api/technicians";
import { scheduleApi } from "@/api/schedule";
import { costAnalysisApi } from "@/api/costAnalysis";
import { eventsApi } from "@/api/events";
import {
  SimulationState,
  MachineContract,
  JobContract,
  TechnicianContract,
  ScheduleResponse,
  CostAnalysisResponse,
  AuditTrailEvent,
  PreemptionEvaluationResponse,
  PreemptionExecuteResponse,
  ReplanRequest,
  SimulationInjectFailureRequest,
} from "@/types/api";

import {
  generateFleet,
  generateActivityEvents,
  PLANTS,
  SHIFTS,
} from "@/lib/data-generator";
import {
  planShift,
  generateCostCurve,
  findOptimalThreshold,
  INSPECTION_COST,
  ALERT_REVIEW_COST,
} from "@/lib/decision-engine";
import { Machine, RiskLevel, DecisionLogEvent } from "@/lib/types";

const DEFAULT_SIM_STATE: SimulationState = {
  status: "running",
  mode: "replay",
  simulated_at: new Date().toISOString(),
  speed: 1,
  last_updated_at: new Date().toISOString(),
  scenario_id: "detroit-assembly-baseline",
  step_count: 42,
};

export function Dashboard() {
  // Navigation & Scope State
  const [currentView, setCurrentView] = useState<NavView>("overview");
  const [selectedPlant, setSelectedPlant] = useState("det-01");
  const [selectedShift, setSelectedShift] = useState("A");
  const [technicianSlots, setTechnicianSlots] = useState(6);
  const [alertThreshold, setAlertThreshold] = useState(0.45);
  const [inspectionCost, setInspectionCost] = useState(INSPECTION_COST);
  const [alertReviewCost, setAlertReviewCost] = useState(ALERT_REVIEW_COST);
  const [runCount, setRunCount] = useState(0);
  const [isScoring, setIsScoring] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("06:00:12");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Selection & Interactivity State
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [pinnedMachineIds, setPinnedMachineIds] = useState<string[]>([]);
  const [selectedRiskFilter, setSelectedRiskFilter] = useState<RiskLevel | "all">("all");
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  // --- Backend Contract State ---
  const [simState, setSimState] = useState<SimulationState>(DEFAULT_SIM_STATE);
  const [isSimLoading, setIsSimLoading] = useState(false);
  const [contractMachines, setContractMachines] = useState<MachineContract[]>([]);
  const [contractJobs, setContractJobs] = useState<JobContract[]>([]);
  const [contractTechnicians, setContractTechnicians] = useState<TechnicianContract[]>([]);
  const [contractSchedule, setContractSchedule] = useState<ScheduleResponse | null>(null);
  const [contractCost, setContractCost] = useState<CostAnalysisResponse | null>(null);
  const [contractEvents, setContractEvents] = useState<AuditTrailEvent[]>([]);

  // Modals & Interactive Workflows
  const [failureModalOpen, setFailureModalOpen] = useState(false);
  const [preemptionModalOpen, setPreemptionModalOpen] = useState(false);
  const [preemptionCurrentJob, setPreemptionCurrentJob] = useState<JobContract | null>(null);
  const [preemptionIncomingJob, setPreemptionIncomingJob] = useState<JobContract | null>(null);
  const [preemptionEvaluation, setPreemptionEvaluation] = useState<PreemptionEvaluationResponse | null>(null);
  const [isEvaluatingPreemption, setIsEvaluatingPreemption] = useState(false);
  const [isReplanning, setIsReplanning] = useState(false);

  // Feedback Toast Helper
  const triggerFeedback = useCallback((msg: string) => {
    setFeedbackMessage(msg);
    setTimeout(() => {
      setFeedbackMessage((prev) => (prev === msg ? null : prev));
    }, 4000);
  }, []);

  // Fetch all Contract Data from Backend API
  const refreshAllContractData = useCallback(async () => {
    try {
      const [sState, sMachines, sJobs, sTechs, sSched, sCost, sEvts] = await Promise.all([
        simulationApi.getState(),
        machinesApi.getAll(),
        jobsApi.getAll(),
        techniciansApi.getAll(),
        scheduleApi.get(),
        costAnalysisApi.get(),
        eventsApi.getAll(),
      ]);
      setSimState(sState);
      setContractMachines(sMachines);
      setContractJobs(sJobs);
      setContractTechnicians(sTechs);
      setContractSchedule(sSched);
      setContractCost(sCost);
      setContractEvents(sEvts);
    } catch (err) {
      console.warn("Error synchronizing contract API data:", err);
    }
  }, []);

  // Poll backend state every 6 seconds to keep live synchronization
  useEffect(() => {
    refreshAllContractData();
    const interval = setInterval(() => {
      refreshAllContractData();
    }, 6000);
    return () => clearInterval(interval);
  }, [refreshAllContractData]);

  // Generate Fleet Data
  const machines = useMemo(() => {
    return generateFleet(selectedPlant, selectedShift, runCount);
  }, [selectedPlant, selectedShift, runCount]);

  // Current Plant Object
  const currentPlant = useMemo(() => {
    return PLANTS.find((p) => p.value === selectedPlant) ?? PLANTS[0];
  }, [selectedPlant]);

  // Run Shift Planner Logic
  const shiftPlan = useMemo(() => {
    return planShift(machines, technicianSlots, alertThreshold, pinnedMachineIds);
  }, [machines, technicianSlots, alertThreshold, pinnedMachineIds]);

  // Compute Cost Curve with adjustable cost parameters
  const costCurve = useMemo(() => {
    return generateCostCurve(machines, technicianSlots, inspectionCost, alertReviewCost);
  }, [machines, technicianSlots, inspectionCost, alertReviewCost]);

  // Find Optimal Threshold Point
  const optimalPoint = useMemo(() => {
    return findOptimalThreshold(costCurve);
  }, [costCurve]);

  // Events Stream
  const [customEvents, setCustomEvents] = useState<DecisionLogEvent[]>([]);
  const baseEvents = useMemo(() => {
    return generateActivityEvents(machines, currentPlant.label);
  }, [machines, currentPlant.label]);

  const allEvents = useMemo(() => {
    return [...customEvents, ...baseEvents];
  }, [customEvents, baseEvents]);

  // Counts & Summaries
  const criticalMachines = useMemo(() => {
    return machines.filter((m) => m.risk === "critical");
  }, [machines]);

  const atRiskCount = useMemo(() => {
    return machines.filter((m) => m.probability >= alertThreshold).length;
  }, [machines, alertThreshold]);

  // Handler: Run Shift Analysis
  const handleRunShiftAnalysis = useCallback(() => {
    setIsScoring(true);
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(
      now.getMinutes()
    ).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

    setTimeout(() => {
      setRunCount((c) => c + 1);
      setLastUpdated(timeStr);
      setIsScoring(false);

      const newEvt: DecisionLogEvent = {
        id: `scoring-${Date.now()}`,
        time: timeStr,
        kind: "prediction",
        message: `Shift Analysis recomputed — ${machines.length} units scored for ${currentPlant.label}`,
      };
      setCustomEvents((prev) => [newEvt, ...prev]);
      triggerFeedback("Shift analysis complete. Telemetry & risk ranking updated.");
    }, 600);
  }, [machines.length, currentPlant.label, triggerFeedback]);

  // Handler: Toggle Pin Machine
  const handleTogglePin = useCallback((machineId: string) => {
    const isCurrentlyPinned = pinnedMachineIds.includes(machineId);
    setPinnedMachineIds((prev) =>
      isCurrentlyPinned
        ? prev.filter((id) => id !== machineId)
        : [...prev, machineId]
    );

    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(
      now.getMinutes()
    ).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;

    const newEvt: DecisionLogEvent = {
      id: `pin-${Date.now()}`,
      time: timeStr,
      kind: "schedule",
      message: isCurrentlyPinned
        ? `${machineId} priority pin removed by operator`
        : `${machineId} manually prioritized and pinned to shift maintenance queue`,
    };
    setCustomEvents((prev) => [newEvt, ...prev]);
    triggerFeedback(
      isCurrentlyPinned
        ? `${machineId} unpinned from shift schedule`
        : `${machineId} prioritized and pinned to slot #1`
    );
  }, [pinnedMachineIds, triggerFeedback]);

  // Handler: Open Machine Details
  const handleSelectMachine = useCallback((m: Machine) => {
    setSelectedMachine(m);
    setIsDrawerOpen(true);
  }, []);

  // Handler: Select contract job & optionally open machine details
  const handleSelectContractJob = useCallback(
    (job: JobContract) => {
      const match = machines.find((m) => m.id === job.machine_id);
      if (match) {
        setSelectedMachine(match);
        setIsDrawerOpen(true);
      } else {
        triggerFeedback(`Job ${job.job_id} on ${job.machine_id}: ${job.status}`);
      }
    },
    [machines, triggerFeedback]
  );

  // --- Simulation Actions (Contract Section 3.A) ---
  const handleSimStart = async () => {
    setIsSimLoading(true);
    try {
      const s = await simulationApi.start({ mode: "replay", speed: 1 });
      setSimState(s);
      triggerFeedback("Simulation started (Replay Mode)");
      await refreshAllContractData();
    } catch (err: any) {
      triggerFeedback(`Simulation error: ${err.message}`);
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleSimPause = async () => {
    setIsSimLoading(true);
    try {
      const s = await simulationApi.pause();
      setSimState(s);
      triggerFeedback("Simulation paused");
    } catch (err: any) {
      triggerFeedback(`Simulation error: ${err.message}`);
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleSimResume = async () => {
    setIsSimLoading(true);
    try {
      const s = await simulationApi.resume();
      setSimState(s);
      triggerFeedback("Simulation resumed");
    } catch (err: any) {
      triggerFeedback(`Simulation error: ${err.message}`);
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleSimStep = async (steps: number) => {
    setIsSimLoading(true);
    try {
      const s = await simulationApi.step({ steps });
      setSimState(s);
      triggerFeedback(`Simulation tick advanced by +${steps * 10} minutes`);
      await refreshAllContractData();
    } catch (err: any) {
      triggerFeedback(`Simulation step error: ${err.message}`);
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleSimReset = async () => {
    setIsSimLoading(true);
    try {
      const s = await simulationApi.reset();
      setSimState(s);
      triggerFeedback("Simulation reset to baseline state");
      await refreshAllContractData();
    } catch (err: any) {
      triggerFeedback(`Reset error: ${err.message}`);
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleInjectFailure = async (machineId: string, scenario: string) => {
    try {
      const res = await simulationApi.injectFailure({
        machine_id: machineId,
        scenario: scenario as SimulationInjectFailureRequest["scenario"],
      });
      triggerFeedback(`Critical Anomaly injected into ${res.machine.name}! Emergency job created.`);
      await refreshAllContractData();
    } catch (err: any) {
      triggerFeedback(`Injection failed: ${err.message}`);
    }
  };

  // --- Pre-emption Workflow (Contract Section 3.F) ---
  const handleStartPreemption = async (activeJob: JobContract) => {
    setPreemptionCurrentJob(activeJob);

    // Pick highest priority incoming job candidate
    const candidate =
      contractJobs.find((j) => j.priority === "critical" && j.job_id !== activeJob.job_id) ||
      contractJobs.find(
        (j) => (j.status === "queued" || j.status === "assigned") && j.job_id !== activeJob.job_id
      ) ||
      null;

    setPreemptionIncomingJob(candidate);
    setPreemptionModalOpen(true);
    setIsEvaluatingPreemption(true);

    try {
      const evalRes = await jobsApi.evaluatePreemption(activeJob.job_id, {
        incoming_job_id: candidate?.job_id || "JOB-URGENT-INCOMING",
        technician_id: activeJob.technician_id || "TECH-01",
      });
      setPreemptionEvaluation(evalRes);
    } catch (err: any) {
      triggerFeedback(`Pre-emption evaluation error: ${err.message}`);
    } finally {
      setIsEvaluatingPreemption(false);
    }
  };

  const handleExecutePreemption = async (
    evaluationId: string,
    incomingJobId: string,
    technicianId: string
  ): Promise<PreemptionExecuteResponse> => {
    if (!preemptionCurrentJob) throw new Error("No active job selected");
    const res = await jobsApi.executePreemption(preemptionCurrentJob.job_id, {
      evaluation_id: evaluationId,
      incoming_job_id: incomingJobId,
      technician_id: technicianId,
    });
    await refreshAllContractData();
    return res;
  };

  // --- Schedule Replanning (Contract Section 3.E) ---
  const handleReplan = async (req: ReplanRequest) => {
    setIsReplanning(true);
    try {
      const res = await scheduleApi.replan(req);
      setContractSchedule(res);
      triggerFeedback("Schedule recalculated with deterministic capacity optimization");
      await refreshAllContractData();
    } catch (err: any) {
      triggerFeedback(`Replanning failed: ${err.message}`);
    } finally {
      setIsReplanning(false);
    }
  };

  // KPI Data Object
  const kpiData = {
    totalMachines: machines.length,
    lineCount: currentPlant.lines.length,
    atRiskCount,
    criticalCount: criticalMachines.length,
    threshold: alertThreshold,
    scheduledSlots: shiftPlan.scheduled.length,
    totalSlots: technicianSlots,
    deferredCount: shiftPlan.deferred.length,
    failureExposure: shiftPlan.totalExposure,
    avoidedExposure: shiftPlan.avoidedExposure,
  };

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar Navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        criticalCount={criticalMachines.length}
        activeJobsCount={contractJobs.filter((j) => j.status === "in_progress").length}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Header */}
        <TopHeader
          currentView={currentView}
          onViewChange={setCurrentView}
          selectedPlant={selectedPlant}
          onPlantChange={(p) => {
            setSelectedPlant(p);
            triggerFeedback(`Switched plant scope to ${p}`);
          }}
          selectedShift={selectedShift}
          onShiftChange={(s) => {
            setSelectedShift(s);
            triggerFeedback(`Active shift set to Shift ${s}`);
          }}
          onRunShiftAnalysis={handleRunShiftAnalysis}
          isScoring={isScoring}
          lastUpdated={lastUpdated}
          onOpenMobile={() => setMobileMenuOpen(true)}
        />

        {/* Global Contract Simulation Control Bar */}
        <SimulationControlBar
          state={simState}
          onStart={handleSimStart}
          onPause={handleSimPause}
          onResume={handleSimResume}
          onStep={handleSimStep}
          onReset={handleSimReset}
          onOpenFailureModal={() => setFailureModalOpen(true)}
          isLoading={isSimLoading}
        />

        {/* Operational Feedback Toast */}
        {feedbackMessage && (
          <div
            role="status"
            className="fixed bottom-5 right-5 z-50 rounded-md border border-border-strong bg-surface px-4 py-2.5 text-sm font-semibold text-foreground shadow-xl transition-all"
          >
            {feedbackMessage}
          </div>
        )}

        {/* Dynamic Page Views */}
        <main className="flex-1 space-y-6 p-6 lg:p-8 max-w-[1920px] mx-auto w-full">
          {/* 1. Overview Command Center (Contract Section 4) */}
          {currentView === "overview" && (
            <>
              {/* Critical Alert Strip with Quick Pre-emption Evaluation Trigger */}
              <CriticalBanner
                criticalMachines={criticalMachines}
                statusById={shiftPlan.statusById}
                onSelectMachine={handleSelectMachine}
              />

              {/* Actionable KPI Row */}
              <KpiRow data={kpiData} />

              {/* Center Row: Machine Risk Ranking + Technician Allocation */}
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
                <div className="xl:col-span-8">
                  <MachineRiskTable
                    machines={machines}
                    statusById={shiftPlan.statusById}
                    onSelectMachine={handleSelectMachine}
                    lines={currentPlant.lines}
                    filterRisk={selectedRiskFilter}
                    onRiskFilterChange={setSelectedRiskFilter}
                  />
                </div>
                <div className="xl:col-span-4">
                  <TechnicianAllocation
                    slots={technicianSlots}
                    onSlotsChange={(newSlots) => {
                      setTechnicianSlots(newSlots);
                      triggerFeedback(`Technician roster adjusted to ${newSlots} slots`);
                    }}
                    threshold={alertThreshold}
                    scheduledMachines={shiftPlan.scheduled}
                    deferredMachines={shiftPlan.deferred}
                    reasonsById={shiftPlan.reasonsById}
                    unmitigatedExposure={shiftPlan.unmitigatedExposure}
                    onSelectMachine={handleSelectMachine}
                  />
                </div>
              </div>

              {/* Bottom Row: Risk Distribution + Cost Curve + Activity */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-12">
                <div className="xl:col-span-4">
                  <RiskDistributionChart
                    machines={machines}
                    selectedRisk={selectedRiskFilter}
                    onSelectRisk={setSelectedRiskFilter}
                  />
                </div>
                <div className="xl:col-span-5">
                  <CostAnalysisChart
                    slots={technicianSlots}
                    costCurve={costCurve}
                    selectedThreshold={alertThreshold}
                    onThresholdChange={(newThresh) => {
                      setAlertThreshold(newThresh);
                      triggerFeedback(
                        `Alert threshold updated to ${Math.round(newThresh * 100)}%`
                      );
                    }}
                    optimalPoint={optimalPoint}
                  />
                </div>
                <div className="lg:col-span-2 xl:col-span-3">
                  <ActivityFeed events={allEvents} />
                </div>
              </div>
            </>
          )}

          {/* 2. Machines Fleet Monitor (Contract Section 4) */}
          {currentView === "machines" && (
            <FleetView
              machines={machines}
              statusById={shiftPlan.statusById}
              onSelectMachine={handleSelectMachine}
              selectedRisk={selectedRiskFilter}
              onSelectRisk={setSelectedRiskFilter}
              lines={currentPlant.lines}
            />
          )}

          {/* 3. Schedule & Gantt Timeline (Contract Section 3.E & 4) */}
          {currentView === "schedule" && (
            <ScheduleGanttView
              assignments={contractSchedule?.assignments ?? []}
              technicians={contractTechnicians}
              unassignedJobIds={contractSchedule?.unassigned_job_ids ?? []}
              jobs={contractJobs}
              onReplan={handleReplan}
              onSelectJob={handleSelectContractJob}
              isReplanning={isReplanning}
            />
          )}

          {/* 4. Maintenance Work Orders & Pre-emption (Contract Section 3.C, 3.F & 4) */}
          {currentView === "jobs" && (
            <JobsView
              jobs={contractJobs}
              onSelectJob={handleSelectContractJob}
              onEvaluatePreemption={handleStartPreemption}
            />
          )}

          {/* 5. Technicians Resource Management (Contract Section 3.D & 4) */}
          {currentView === "technicians" && (
            <TechniciansView
              technicians={contractTechnicians}
              jobs={contractJobs}
              onSelectJob={handleSelectContractJob}
            />
          )}

          {/* 6. Cost Analysis & Option Comparison (Contract Section 3.H & 4) */}
          {currentView === "cost" && (
            <>
              {contractCost ? (
                <ContractCostView costAnalysis={contractCost} />
              ) : (
                <div className="panel p-8 text-center text-foreground-muted">
                  Loading cost optimization model from backend...
                </div>
              )}
            </>
          )}

          {/* 7. Event Stream & Audit Trail (Contract Section 3.G & 4) */}
          {currentView === "logs" && (
            <AuditLogView
              events={contractEvents}
              onSelectMachineId={(mId) => {
                const match = machines.find((m) => m.id === mId);
                if (match) handleSelectMachine(match);
              }}
              onSelectJobId={(jId) => {
                const job = contractJobs.find((j) => j.job_id === jId);
                if (job) handleSelectContractJob(job);
              }}
            />
          )}

          {/* 8. Three-Stage Decision Engine Framework */}
          {currentView === "engine" && (
            <DecisionEngineView
              machines={machines}
              slots={technicianSlots}
              onSlotsChange={(newSlots) => {
                setTechnicianSlots(newSlots);
                triggerFeedback(`Capacity updated to ${newSlots} slots`);
              }}
              threshold={alertThreshold}
              onThresholdChange={(newThresh) => {
                setAlertThreshold(newThresh);
                triggerFeedback(`Threshold set to ${Math.round(newThresh * 100)}%`);
              }}
              shiftPlan={shiftPlan}
              costCurve={costCurve}
              optimalPoint={optimalPoint}
              inspectionCost={inspectionCost}
              onInspectionCostChange={(cost) => {
                setInspectionCost(cost);
                triggerFeedback(`Dispatch cost adjusted to $${cost}`);
              }}
              alertReviewCost={alertReviewCost}
              onAlertReviewCostChange={(cost) => {
                setAlertReviewCost(cost);
                triggerFeedback(`Review cost adjusted to $${cost}`);
              }}
              pinnedIds={pinnedMachineIds}
              onTogglePin={handleTogglePin}
              onSelectMachine={handleSelectMachine}
            />
          )}

          {/* Truthful Editorial Footer Disclosure */}
          <footer className="pt-6 pb-4 text-center text-xs text-foreground-muted border-t border-border-subtle select-none">
            ForgeGuard Predictive Maintenance Platform · Demonstrator Prototype · All telemetry and costs represent simulated operational models.
          </footer>
        </main>
      </div>

      {/* Machine Detail Overlay Drawer */}
      <MachineDetailDrawer
        machine={selectedMachine}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        status={
          selectedMachine ? shiftPlan.statusById.get(selectedMachine.id) : undefined
        }
        isPinned={
          selectedMachine ? pinnedMachineIds.includes(selectedMachine.id) : false
        }
        onTogglePin={handleTogglePin}
      />

      {/* Pre-emption Evaluation & Execution Hard-Gate Modal */}
      <PreemptionModal
        isOpen={preemptionModalOpen}
        onClose={() => setPreemptionModalOpen(false)}
        currentJob={preemptionCurrentJob}
        incomingJob={preemptionIncomingJob}
        evaluation={preemptionEvaluation}
        isEvaluating={isEvaluatingPreemption}
        onExecute={handleExecutePreemption}
        onSuccess={(msg) => triggerFeedback(msg)}
      />

      {/* Demo Scenario Failure Injection Modal */}
      <InjectFailureModal
        isOpen={failureModalOpen}
        onClose={() => setFailureModalOpen(false)}
        machines={contractMachines}
        onInject={handleInjectFailure}
      />
    </div>
  );
}
