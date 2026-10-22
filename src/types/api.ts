/**
 * FORGEGUARD — UI LAYER & BACKEND INTEGRATION CONTRACT v1.0
 * Type definitions strictly adhering to the specification.
 */

// -------------------------------------------------------------
// Simulation Lifecycle Types (Section 3.A)
// -------------------------------------------------------------
export type SimulationStatus = "running" | "paused" | "stopped";
export type SimulationMode = "replay" | "demo" | "live";

export interface SimulationState {
  status: SimulationStatus;
  mode: SimulationMode;
  simulated_at: string; // ISO-8601
  speed: number;
  last_updated_at: string; // ISO-8601
  scenario_id?: string;
  step_count?: number;
}

export interface SimulationStartRequest {
  mode: SimulationMode;
  speed?: number;
  scenario_id?: string;
}

export interface SimulationStepRequest {
  steps?: number;
}

export interface SimulationInjectFailureRequest {
  machine_id: string;
  scenario: "critical_failure" | "thermal_runaway" | "bearing_seizure" | "hydraulic_drop";
  severity?: "high" | "critical";
}

// -------------------------------------------------------------
// Machine Types (Section 3.B)
// -------------------------------------------------------------
export type MachineStatus = "healthy" | "watch" | "maintenance_due" | "critical" | "unknown";
export type SafetyStatus = "safe" | "unsafe" | "indeterminate" | "unknown";
export type DecisionType = "monitor" | "schedule_maintenance" | "urgent_maintenance" | "unknown";

export interface MachineTelemetrySummary {
  vibration: number; // mm/s
  airTemp: number; // K
  processTemp: number; // K
  rpm: number; // RPM
  torque: number; // Nm
  toolWear: number; // min
}

export interface MachineContract {
  machine_id: string;
  name: string;
  line: string;
  type: string;
  status: MachineStatus;
  failure_probability: number; // 0.0 - 1.0
  predicted_failure_mode?: string;
  last_telemetry_at: string; // ISO-8601
  decision: DecisionType;
  remaining_useful_life_hours: number | null;
  safety_status: SafetyStatus;
  active_job_id: string | null;
  failure_cost: number;
  telemetry: MachineTelemetrySummary;
  features: Array<{ feature: string; impact: number; value: string }>;
  trend: Array<{ hour: string; probability: number }>;
}

// -------------------------------------------------------------
// Jobs & Maintenance Types (Section 3.C)
// -------------------------------------------------------------
export type JobType = "inspection" | "preventive" | "corrective";
export type JobPriority = "low" | "medium" | "high" | "critical";
export type JobStatus = "queued" | "assigned" | "in_progress" | "paused" | "completed" | "blocked";

export interface JobContract {
  job_id: string;
  machine_id: string;
  machine_name?: string;
  job_type: JobType;
  priority: JobPriority;
  status: JobStatus;
  technician_id: string | null;
  technician_name?: string | null;
  estimated_duration_minutes: number;
  elapsed_minutes: number;
  progress_percent: number;
  estimated_maintenance_cost: number;
  estimated_downtime_cost: number;
  safety_status: SafetyStatus;
  is_preempted?: boolean;
  preempted_reason?: string;
  created_at: string; // ISO-8601
  updated_at: string; // ISO-8601
  description: string;
}

// -------------------------------------------------------------
// Technician Types (Section 3.D)
// -------------------------------------------------------------
export type TechnicianStatus = "available" | "assigned" | "on_job" | "unavailable";

export interface TechnicianContract {
  technician_id: string;
  name: string;
  role: string;
  status: TechnicianStatus;
  skills: string[];
  current_job_id: string | null;
  current_job_name?: string | null;
  estimated_available_at: string | null; // ISO-8601 or null
  shift: string;
  efficiency_rating: number; // e.g. 0.95
  completed_jobs_count: number;
}

// -------------------------------------------------------------
// Schedule & Replanning Types (Section 3.E)
// -------------------------------------------------------------
export type ScheduleAssignmentStatus = "planned" | "in_progress" | "paused" | "completed";

export interface ScheduleAssignment {
  job_id: string;
  machine_id: string;
  technician_id: string;
  technician_name?: string;
  planned_start_at: string; // ISO-8601
  planned_end_at: string; // ISO-8601
  actual_start_at?: string;
  actual_end_at?: string;
  status: ScheduleAssignmentStatus;
  reason?: string;
  priority: JobPriority;
  job_type: JobType;
}

export interface ScheduleResponse {
  generated_at: string; // ISO-8601
  shift_name: string;
  assignments: ScheduleAssignment[];
  unassigned_job_ids: string[];
  conflicts: Array<{ description: string; job_id: string; technician_id: string }>;
}

export interface ReplanRequest {
  reason: "new_critical_job" | "technician_unavailable" | "end_of_shift_rebalance" | "operator_override";
  trigger_job_id?: string;
}

// -------------------------------------------------------------
// Pre-emption Workflow Types (Section 3.F)
// -------------------------------------------------------------
export type PreemptionDecision = "allow" | "deny" | "needs_review";

export interface PreemptionAlternative {
  action: "finish_current_job" | "preempt" | "assign_other_technician" | "defer_incoming_job";
  label: string;
  estimated_total_cost: number | null;
  feasible: boolean;
  reason: string;
}

export interface PreemptionEvaluationRequest {
  incoming_job_id: string;
  technician_id: string;
}

export interface PreemptionEvaluationResponse {
  evaluation_id: string;
  current_job: JobContract;
  incoming_job: JobContract;
  decision: PreemptionDecision;
  safe_to_interrupt: boolean;
  safety_status: SafetyStatus;
  reason_codes: string[];
  explanation: string;
  estimated_interruption_cost: number | null;
  alternatives: PreemptionAlternative[];
  evaluated_at: string;
}

export interface PreemptionExecuteRequest {
  evaluation_id: string;
  incoming_job_id: string;
  technician_id: string;
  reason?: string;
}

export interface PreemptionExecuteResponse {
  success: boolean;
  message: string;
  preempted_job_id: string;
  new_active_job_id: string;
  technician_id: string;
  timestamp: string;
}

// -------------------------------------------------------------
// Cost Analysis Types (Section 3.H)
// -------------------------------------------------------------
export interface CostAnalysisOption {
  option_id: "maintain_now" | "delay_one_shift" | "defer_weekend" | "emergency_interruption";
  label: string;
  maintenance_cost: number | null;
  downtime_cost: number | null;
  delay_risk_cost: number | null;
  interruption_cost: number | null;
  total_estimated_cost: number | null;
  feasible: boolean;
  assumptions: string[];
}

export interface CostAnalysisResponse {
  currency: string;
  generated_at: string;
  options: CostAnalysisOption[];
  recommended_option_id: string;
  explanation: string;
  parameters: {
    inspection_dispatch_fee: number;
    alert_review_overhead: number;
    hourly_downtime_cost: number;
    technician_rate: number;
  };
}

// -------------------------------------------------------------
// Audit Trail & Events (Section 3.G)
// -------------------------------------------------------------
export type EventSeverity = "info" | "warning" | "critical" | "decision";
export type EventCategory = "prediction" | "safety" | "schedule" | "preemption" | "simulation" | "job";

export interface AuditTrailEvent {
  id: string;
  timestamp: string; // ISO-8601
  severity: EventSeverity;
  category: EventCategory;
  title: string;
  message: string;
  machine_id?: string;
  job_id?: string;
  technician_id?: string;
  actor: "engine" | "orchestration" | "operator";
  metadata?: Record<string, unknown>;
}

// -------------------------------------------------------------
// Shared API Response Convention (Section 2)
// -------------------------------------------------------------
export interface ApiResponse<T> {
  data: T;
  request_id: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
  request_id: string;
}
