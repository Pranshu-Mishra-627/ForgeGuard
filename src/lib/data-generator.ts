import {
  PlantOption,
  ShiftOption,
  Machine,
  FailureMode,
  RiskLevel,
  Telemetry,
  DecisionLogEvent,
} from "./types";

export const PLANTS: PlantOption[] = [
  {
    value: "det-01",
    label: "Detroit Stamping · P1",
    lines: ["Press Line A", "Press Line B", "Weld Cell 3", "Paint Shop"],
  },
  {
    value: "mty-02",
    label: "Monterrey Assembly · P2",
    lines: ["Body Line 1", "Body Line 2", "Final Assembly", "Molding Bay"],
  },
  {
    value: "stg-03",
    label: "Stuttgart Powertrain · P3",
    lines: ["Machining Hall", "Gear Cell", "Casting", "Test Bench"],
  },
];

export const SHIFTS: ShiftOption[] = [
  { value: "A", label: "Shift A · 06:00–14:00" },
  { value: "B", label: "Shift B · 14:00–22:00" },
  { value: "C", label: "Shift C · 22:00–06:00" },
];

interface MachineTypeConfig {
  type: string;
  prefix: string;
  cost: [number, number];
  modes: FailureMode[];
}

const MACHINE_TYPES: MachineTypeConfig[] = [
  {
    type: "CNC Mill",
    prefix: "CNC",
    cost: [38000, 72000],
    modes: ["Tool Wear Failure", "Overstrain Failure", "Heat Dissipation Failure"],
  },
  {
    type: "Hydraulic Press",
    prefix: "HPR",
    cost: [95000, 180000],
    modes: ["Hydraulic Leak", "Overstrain Failure", "Power Failure"],
  },
  {
    type: "Robotic Welder",
    prefix: "RWD",
    cost: [52000, 96000],
    modes: ["Power Failure", "Heat Dissipation Failure", "Bearing Degradation"],
  },
  {
    type: "Conveyor Drive",
    prefix: "CNV",
    cost: [18000, 41000],
    modes: ["Bearing Degradation", "Power Failure"],
  },
  {
    type: "Air Compressor",
    prefix: "CMP",
    cost: [24000, 58000],
    modes: ["Heat Dissipation Failure", "Bearing Degradation"],
  },
  {
    type: "Injection Molder",
    prefix: "INJ",
    cost: [64000, 128000],
    modes: ["Heat Dissipation Failure", "Hydraulic Leak", "Tool Wear Failure"],
  },
];

const FAILURE_METADATA: Record<
  FailureMode,
  { action: string; reason: string; feature: string }
> = {
  "Tool Wear Failure": {
    action: "Replace cutting tool & recalibrate spindle",
    reason: "Tool wear beyond 200 min envelope",
    feature: "Tool wear",
  },
  "Heat Dissipation Failure": {
    action: "Clean heat exchanger, verify coolant flow",
    reason: "Process–air ΔT collapsing",
    feature: "Temp differential",
  },
  "Power Failure": {
    action: "Inspect drive & power electronics",
    reason: "Power draw outside 3.5–9 kW band",
    feature: "Power (torque × rpm)",
  },
  "Overstrain Failure": {
    action: "Reduce load, inspect gearbox & tooling",
    reason: "Torque × wear above strain limit",
    feature: "Strain index",
  },
  "Bearing Degradation": {
    action: "Replace bearings, re-grease, align shaft",
    reason: "Vibration RMS trending upward",
    feature: "Vibration RMS",
  },
  "Hydraulic Leak": {
    action: "Pressure-test lines, replace seals",
    reason: "Pressure decay during hold cycle",
    feature: "Pressure decay",
  },
};

const TECHNICIANS = [
  "R. Okafor",
  "M. Lindqvist",
  "J. Alvarez",
  "S. Tanaka",
  "D. Kowalski",
  "A. Haddad",
];

const MAINTENANCE_ACTIONS = [
  "Preventive inspection — no defects",
  "Lubrication & filter service",
  "Replaced worn belt assembly",
  "Firmware update on PLC controller",
  "Sensor recalibration",
  "Coolant system flush",
];

const PAST_DATES = [
  "2026-10-14",
  "2026-09-29",
  "2026-09-03",
  "2026-08-11",
  "2026-07-22",
];

function fnv1a(str: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x1000193);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  let t = seed;
  return () => {
    t |= 0;
    let s = Math.imul((t = (t + 0x6d2b79f5) | 0) ^ (t >>> 15), 1 | t);
    return (
      ((s = (s + Math.imul(s ^ (s >>> 7), 61 | s)) ^ s) ^ (s >>> 14)) >>> 0
    ) / 0x100000000;
  };
}

const clamp = (val: number, min: number, max: number) =>
  Math.min(max, Math.max(min, val));

const round = (val: number, decimals = 0) => {
  const factor = 10 ** decimals;
  return Math.round(val * factor) / factor;
};

export function getRiskLevel(probability: number): RiskLevel {
  if (probability >= 0.7) return "critical";
  if (probability >= 0.45) return "high";
  if (probability >= 0.2) return "medium";
  return "low";
}

const ACTION_TIMELINE: Record<RiskLevel, string> = {
  critical: "Immediate",
  high: "This shift",
  medium: "Within 72h",
  low: "Monitor",
};

function formatFeatureValue(feature: string, t: Telemetry): string {
  switch (feature) {
    case "Tool wear":
      return `${t.toolWear} min`;
    case "Temp differential":
      return `${round(t.processTemp - t.airTemp, 1)} K`;
    case "Power (torque × rpm)":
      return `${round((t.torque * t.rpm * 2 * Math.PI) / 60 / 1000, 2)} kW`;
    case "Strain index":
      return `${Math.round(t.torque * t.toolWear)} Nm·min`;
    case "Vibration RMS":
      return `${t.vibration} mm/s`;
    case "Pressure decay":
      return `${round(0.9 * t.vibration, 1)} bar/min`;
    case "Torque":
      return `${t.torque} Nm`;
    case "Rotational speed":
      return `${t.rpm} rpm`;
    case "Process temp":
      return `${t.processTemp} K`;
    case "Air temp":
      return `${t.airTemp} K`;
    default:
      return `${Math.round(1.7 * t.toolWear)} h`;
  }
}

export function generateFleet(
  plantId: string,
  shiftId: string,
  runCount = 0
): Machine[] {
  const plant = PLANTS.find((p) => p.value === plantId) ?? PLANTS[0];
  const rand = mulberry32(fnv1a(`${plantId}:${shiftId}`));
  const randRun = mulberry32(fnv1a(`${plantId}:${shiftId}:run${runCount}`));

  const idCounters: Record<string, number> = {};

  const machines: Machine[] = Array.from({ length: 36 }, (_, idx) => {
    const config =
      MACHINE_TYPES[Math.floor(rand() * MACHINE_TYPES.length)];
    idCounters[config.prefix] =
      (idCounters[config.prefix] ?? 100) + 1 + Math.floor(6 * rand());
    const id = `${config.prefix}-${idCounters[config.prefix]}`;
    const line = plant.lines[idx % plant.lines.length];

    const baseProb = clamp(1.04 * Math.pow(rand(), 2.4), 0.01, 0.97);
    const probDelta = (randRun() - 0.5) * 0.07 * (runCount > 0 ? 1 : 0);
    const probability = round(clamp(baseProb + probDelta, 0.01, 0.98), 3);

    const failureMode =
      config.modes[Math.floor(rand() * config.modes.length)];
    const risk = getRiskLevel(probability);
    const failureCost =
      500 *
      Math.round(
        (config.cost[0] + rand() * (config.cost[1] - config.cost[0])) / 500
      );

    const meta = FAILURE_METADATA[failureMode];

    const airTemp = round(298 + 4 * rand(), 1);
    const processTemp = round(
      airTemp +
        (failureMode === "Heat Dissipation Failure"
          ? 10 - 4 * probability
          : 9.5 + 2 * rand()),
      1
    );
    const rpm = Math.round(
      failureMode === "Power Failure"
        ? 1250 + 1300 * probability * (rand() > 0.5 ? 1 : -0.1)
        : 1380 + 420 * rand()
    );
    const torque = round(
      failureMode === "Overstrain Failure" || failureMode === "Power Failure"
        ? 40 + 28 * probability
        : 32 + 14 * rand(),
      1
    );
    const toolWear = Math.round(
      failureMode === "Tool Wear Failure" || failureMode === "Overstrain Failure"
        ? 90 + 150 * probability
        : 20 + 120 * rand()
    );
    const vibration = round(
      failureMode === "Bearing Degradation"
        ? 2.2 + 6.5 * probability
        : 1.4 + 1.8 * rand(),
      2
    );

    const telemetry: Telemetry = {
      airTemp,
      processTemp,
      rpm,
      torque,
      toolWear,
      vibration,
    };

    const candidateFeatures = [
      "Tool wear",
      "Torque",
      "Rotational speed",
      "Process temp",
      "Air temp",
      "Vibration RMS",
      "Runtime since PM",
    ].filter((f) => f !== meta.feature);

    // Shuffle candidate features
    const shuffled = [...candidateFeatures];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }

    const otherFeatures = shuffled.slice(0, 4);
    const features = [
      {
        feature: meta.feature,
        value: formatFeatureValue(meta.feature, telemetry),
        impact: round(0.18 + 0.42 * probability, 2),
      },
      ...otherFeatures.map((feat, i) => ({
        feature: feat,
        value: formatFeatureValue(feat, telemetry),
        impact: round(
          (i === 3 ? -1 : 1) * (0.04 + 0.16 * rand()) * (1 - 0.18 * i),
          2
        ),
      })),
    ].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));

    // 24h trend
    let startProb = probability * (0.35 + 0.35 * rand());
    const trend = Array.from({ length: 24 }, (_, i) => {
      startProb =
        i === 23
          ? probability
          : clamp(
              startProb + (probability - startProb) * 0.14 + (rand() - 0.45) * 0.03,
              0.005,
              0.99
            );
      const hourNum = (i + 7) % 24;
      return {
        hour: `${String(hourNum).padStart(2, "0")}:00`,
        probability: round(startProb, 3),
      };
    });

    const historyCount = 3 + Math.floor(2 * rand());
    const history = PAST_DATES.slice(0, historyCount).map((d) => ({
      date: d,
      action:
        MAINTENANCE_ACTIONS[
          Math.floor(rand() * MAINTENANCE_ACTIONS.length)
        ],
      technician: TECHNICIANS[Math.floor(rand() * TECHNICIANS.length)],
    }));

    const recAction =
      risk === "low"
        ? "continue condition monitoring"
        : meta.action.toLowerCase();

    return {
      id,
      type: config.type,
      line,
      probability,
      failureMode,
      risk,
      recommendation: `${ACTION_TIMELINE[risk]} — ${recAction}`,
      reason: meta.reason,
      failureCost,
      priority: 0,
      telemetry,
      trend,
      features,
      history,
    };
  });

  // Calculate cost-weighted priority score
  const maxImpact = Math.max(...machines.map((m) => m.probability * m.failureCost));
  for (const m of machines) {
    m.priority = Math.round(
      (m.probability * m.failureCost / (maxImpact || 1)) * 100
    );
  }

  return machines.sort((a, b) => b.priority - a.priority);
}

export function generateActivityEvents(
  machines: Machine[],
  plantLabel: string
): DecisionLogEvent[] {
  const critical = machines.filter((m) => m.risk === "critical");
  return [
    {
      id: "e1",
      time: "06:00:12",
      kind: "prediction",
      message: `Batch scoring complete — ${machines.length} machines evaluated for ${plantLabel}`,
    },
    ...critical.slice(0, 3).map((m, idx) => ({
      id: `e-crit-${m.id}`,
      time: `05:5${8 - idx}:4${idx}`,
      kind: "alert" as const,
      message: `${m.id} exceeded alert threshold — ${m.failureMode.toLowerCase()} at ${Math.round(
        100 * m.probability
      )}%`,
    })),
    {
      id: "e2",
      time: "05:52:03",
      kind: "schedule",
      message: "Shift A technician roster synced — 6 slots allocated",
    },
    {
      id: "e3",
      time: "05:45:30",
      kind: "system",
      message: "Telemetry pipeline operating within nominal tolerances (1.2M readings/hr)",
    },
    {
      id: "e4",
      time: "05:30:00",
      kind: "prediction",
      message: "Model fg-gbm v3.2 active — validation AUC 0.94, Recall@45% 0.88",
    },
    {
      id: "e5",
      time: "04:12:19",
      kind: "schedule",
      message: `${machines[5]?.id ?? "CNC-118"} scheduled maintenance signed off by S. Tanaka`,
    },
  ];
}

export function formatCurrency(amount: number, compact = true): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 0,
  }).format(amount);
}
