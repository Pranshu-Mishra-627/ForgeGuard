export type RiskLevel = "critical" | "high" | "medium" | "low";

export type FailureMode =
  | "Tool Wear Failure"
  | "Heat Dissipation Failure"
  | "Power Failure"
  | "Overstrain Failure"
  | "Bearing Degradation"
  | "Hydraulic Leak";

export interface Telemetry {
  airTemp: number; // K
  processTemp: number; // K
  rpm: number; // RPM
  torque: number; // Nm
  toolWear: number; // min
  vibration: number; // mm/s
}

export interface FeatureImpact {
  feature: string;
  value: string;
  impact: number;
}

export interface MaintenanceRecord {
  date: string;
  action: string;
  technician: string;
}

export interface TrendPoint {
  hour: string;
  probability: number;
}

export interface Machine {
  id: string;
  type: string;
  line: string;
  probability: number;
  failureMode: FailureMode;
  risk: RiskLevel;
  recommendation: string;
  reason: string;
  failureCost: number;
  priority: number; // 0 - 100 cost-weighted score
  telemetry: Telemetry;
  trend: TrendPoint[];
  features: FeatureImpact[];
  history: MaintenanceRecord[];
}

export type MachineStatus = "scheduled" | "deferred" | "unalerted";

export interface PlantOption {
  value: string;
  label: string;
  lines: string[];
}

export interface ShiftOption {
  value: string;
  label: string;
}

export interface ShiftPlanResult {
  ranked: Machine[];
  scheduled: Machine[];
  deferred: Machine[];
  statusById: Map<string, "scheduled" | "deferred">;
  reasonsById: Map<string, string>;
  totalExposure: number;
  avoidedExposure: number;
  unmitigatedExposure: number;
}

export interface DecisionLogEvent {
  id: string;
  time: string;
  kind: "prediction" | "alert" | "schedule" | "system";
  message: string;
}

export interface ThresholdCostPoint {
  threshold: number;
  cost: number;
  failureCost: number;
  maintenanceCost: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
}
