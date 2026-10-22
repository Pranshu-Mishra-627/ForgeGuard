import {
  MachineContract,
  JobContract,
  TechnicianContract,
  ScheduleAssignment,
  ScheduleResponse,
  SimulationState,
  AuditTrailEvent,
  CostAnalysisResponse,
  PreemptionEvaluationResponse,
  PreemptionExecuteResponse,
  ReplanRequest,
} from "@/types/api";

// Helper to generate IDs and timestamps
function generateId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
}

function getSimulatedTimestamp(offsetMinutes = 0): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() + offsetMinutes);
  return d.toISOString();
}

class SimulationStore {
  private static instance: SimulationStore;

  public state: SimulationState = {
    status: "running",
    mode: "replay",
    simulated_at: getSimulatedTimestamp(),
    speed: 1,
    last_updated_at: getSimulatedTimestamp(),
    scenario_id: "detroit-assembly-baseline",
    step_count: 42,
  };

  public machines: MachineContract[] = [];
  public jobs: JobContract[] = [];
  public technicians: TechnicianContract[] = [];
  public schedule: ScheduleAssignment[] = [];
  public events: AuditTrailEvent[] = [];
  private evaluations = new Map<string, PreemptionEvaluationResponse>();

  private constructor() {
    this.initializeBaselineData();
  }

  public static getInstance(): SimulationStore {
    if (!SimulationStore.instance) {
      SimulationStore.instance = new SimulationStore();
    }
    return SimulationStore.instance;
  }

  private initializeBaselineData() {
    // 1. Initialize Technicians (Contract Section 3.D)
    this.technicians = [
      {
        technician_id: "TECH-01",
        name: "Marcus Vance",
        role: "Senior Mechanical Specialist",
        status: "on_job",
        skills: ["Vibration Analysis", "Spindle Rebuild", "LOTO Cert Level 3"],
        current_job_id: "JOB-101",
        current_job_name: "Spindle Bearing Replacement",
        estimated_available_at: getSimulatedTimestamp(45),
        shift: "Shift A (Morning)",
        efficiency_rating: 0.98,
        completed_jobs_count: 142,
      },
      {
        technician_id: "TECH-02",
        name: "Elena Rostova",
        role: "Hydraulics & Robotics Tech",
        status: "on_job",
        skills: ["Hydraulic Servos", "Robotic Kinematics", "Fluid Flushing"],
        current_job_id: "JOB-102",
        current_job_name: "Hydraulic Pump Cavitation Overhaul",
        estimated_available_at: getSimulatedTimestamp(70),
        shift: "Shift A (Morning)",
        efficiency_rating: 0.94,
        completed_jobs_count: 98,
      },
      {
        technician_id: "TECH-03",
        name: "Devon Brooks",
        role: "Electrical & Inverter Engineer",
        status: "available",
        skills: ["Drive Inverters", "Thermal Diagnostics", "PLC Controls"],
        current_job_id: null,
        current_job_name: null,
        estimated_available_at: getSimulatedTimestamp(0),
        shift: "Shift A (Morning)",
        efficiency_rating: 0.96,
        completed_jobs_count: 115,
      },
      {
        technician_id: "TECH-04",
        name: "Priya Sharma",
        role: "Predictive Reliability Analyst",
        status: "available",
        skills: ["Acoustic Ultrasound", "Laser Alignment", "Tool Balancer"],
        current_job_id: null,
        current_job_name: null,
        estimated_available_at: getSimulatedTimestamp(0),
        shift: "Shift A (Morning)",
        efficiency_rating: 0.99,
        completed_jobs_count: 167,
      },
      {
        technician_id: "TECH-05",
        name: "Carlos Mendez",
        role: "Mechanical Millwright",
        status: "assigned",
        skills: ["Gearbox Rebuild", "Shaft Coupling", "Heavy Rigging"],
        current_job_id: "JOB-103",
        current_job_name: "Drive Shaft Coupling Realignment",
        estimated_available_at: getSimulatedTimestamp(90),
        shift: "Shift A (Morning)",
        efficiency_rating: 0.91,
        completed_jobs_count: 84,
      },
      {
        technician_id: "TECH-06",
        name: "Hannah Lindqvist",
        role: "Safety & Compliance Officer",
        status: "available",
        skills: ["OSHA Lockout", "Pressure Vessel Inspection", "Arc Flash"],
        current_job_id: null,
        current_job_name: null,
        estimated_available_at: getSimulatedTimestamp(0),
        shift: "Shift A (Morning)",
        efficiency_rating: 1.0,
        completed_jobs_count: 210,
      },
    ];

    // 2. Initialize Machines (Contract Section 3.B)
    const machineTemplates = [
      {
        id: "M-03",
        name: "Hydraulic Press 03",
        line: "Line 1 — Stamping & Blanking",
        type: "Hydraulic Press",
        status: "critical" as const,
        prob: 0.88,
        mode: "Hydraulic Pump Cavitation & Seal Degradation",
        decision: "urgent_maintenance" as const,
        safety: "unsafe" as const,
        cost: 48000,
        active_job: "JOB-102",
        vib: 4.82,
        airT: 301.2,
        procT: 312.4,
        rpm: 1410,
        torque: 58.2,
        tool: 184,
      },
      {
        id: "M-07",
        name: "CNC Milling Center 07",
        line: "Line 2 — Precision Machining",
        type: "CNC Milling Center",
        status: "critical" as const,
        prob: 0.82,
        mode: "Spindle Bearing Race Fatigue",
        decision: "urgent_maintenance" as const,
        safety: "safe" as const, // Safe to interrupt if needed!
        cost: 42000,
        active_job: "JOB-101",
        vib: 4.35,
        airT: 299.8,
        procT: 309.1,
        rpm: 1530,
        torque: 46.1,
        tool: 202,
      },
      {
        id: "M-11",
        name: "Robotic Welder Cell 11",
        line: "Line 3 — BIW Robotic Welding",
        type: "Robotic Welder",
        status: "maintenance_due" as const,
        prob: 0.64,
        mode: "Power Inverter Thermal Dissipation",
        decision: "schedule_maintenance" as const,
        safety: "safe" as const,
        cost: 32000,
        active_job: "JOB-104",
        vib: 2.12,
        airT: 302.5,
        procT: 314.8,
        rpm: 1380,
        torque: 39.4,
        tool: 140,
      },
      {
        id: "M-14",
        name: "Conveyor Drive 14",
        line: "Line 4 — Main Transfer Conveyor",
        type: "Conveyor Drive",
        status: "maintenance_due" as const,
        prob: 0.58,
        mode: "Drive Shaft Coupling Misalignment",
        decision: "schedule_maintenance" as const,
        safety: "safe" as const,
        cost: 26000,
        active_job: "JOB-103",
        vib: 3.15,
        airT: 298.4,
        procT: 306.2,
        rpm: 1490,
        torque: 42.8,
        tool: 115,
      },
      {
        id: "M-02",
        name: "Stamping Press 02",
        line: "Line 1 — Stamping & Blanking",
        type: "Stamping Press",
        status: "watch" as const,
        prob: 0.38,
        mode: "Tool Chipping & Clearance Drift",
        decision: "monitor" as const,
        safety: "safe" as const,
        cost: 28000,
        active_job: null,
        vib: 2.45,
        airT: 299.1,
        procT: 308.2,
        rpm: 1510,
        torque: 41.2,
        tool: 95,
      },
      {
        id: "M-05",
        name: "Pick & Place Gantry 05",
        line: "Line 2 — Precision Machining",
        type: "Gantry Robot",
        status: "healthy" as const,
        prob: 0.12,
        mode: "Normal Wear Pattern",
        decision: "monitor" as const,
        safety: "safe" as const,
        cost: 18000,
        active_job: null,
        vib: 1.15,
        airT: 298.0,
        procT: 305.1,
        rpm: 1450,
        torque: 34.0,
        tool: 45,
      },
      {
        id: "M-09",
        name: "Induction Heating Unit 09",
        line: "Line 3 — BIW Robotic Welding",
        type: "Induction Furnace",
        status: "watch" as const,
        prob: 0.42,
        mode: "Coolant Loop Flow Restriction",
        decision: "monitor" as const,
        safety: "indeterminate" as const, // Indeterminate safety check
        cost: 36000,
        active_job: null,
        vib: 1.95,
        airT: 303.4,
        procT: 317.0,
        rpm: 1420,
        torque: 37.5,
        tool: 88,
      },
      {
        id: "M-16",
        name: "Automated Guided Cart 16",
        line: "Line 4 — Main Transfer Conveyor",
        type: "AGV Transport",
        status: "healthy" as const,
        prob: 0.08,
        mode: "Nominal Operating Profile",
        decision: "monitor" as const,
        safety: "safe" as const,
        cost: 12000,
        active_job: null,
        vib: 0.95,
        airT: 297.5,
        procT: 304.2,
        rpm: 1440,
        torque: 31.0,
        tool: 30,
      },
    ];

    this.machines = machineTemplates.map((t) => ({
      machine_id: t.id,
      name: t.name,
      line: t.line,
      type: t.type,
      status: t.status,
      failure_probability: t.prob,
      predicted_failure_mode: t.mode,
      last_telemetry_at: getSimulatedTimestamp(-2),
      decision: t.decision,
      remaining_useful_life_hours: t.status === "critical" ? 14 : t.status === "maintenance_due" ? 48 : 120,
      safety_status: t.safety,
      active_job_id: t.active_job,
      failure_cost: t.cost,
      telemetry: {
        vibration: t.vib,
        airTemp: t.airT,
        processTemp: t.procT,
        rpm: t.rpm,
        torque: t.torque,
        toolWear: t.tool,
      },
      features: [
        { feature: "Vibration RMS [mm/s]", impact: +(t.vib * 0.18).toFixed(2), value: `${t.vib} mm/s` },
        { feature: "Temperature Delta ΔT", impact: +((t.procT - t.airT) * 0.04).toFixed(2), value: `${(t.procT - t.airT).toFixed(1)} K` },
        { feature: "Tool Wear Accumulation", impact: +(t.tool * 0.002).toFixed(2), value: `${t.tool} min` },
        { feature: "Torque Ripple Variance", impact: +(t.torque * 0.012).toFixed(2), value: `${t.torque} Nm` },
      ],
      trend: [
        { hour: "-24h", probability: +(t.prob * 0.35).toFixed(2) },
        { hour: "-18h", probability: +(t.prob * 0.48).toFixed(2) },
        { hour: "-12h", probability: +(t.prob * 0.62).toFixed(2) },
        { hour: "-6h", probability: +(t.prob * 0.81).toFixed(2) },
        { hour: "-1h", probability: +(t.prob * 0.95).toFixed(2) },
        { hour: "Now", probability: t.prob },
      ],
    }));

    // 3. Initialize Jobs (Contract Section 3.C)
    this.jobs = [
      {
        job_id: "JOB-101",
        machine_id: "M-07",
        machine_name: "CNC Milling Center 07",
        job_type: "corrective",
        priority: "critical",
        status: "in_progress",
        technician_id: "TECH-01",
        technician_name: "Marcus Vance",
        estimated_duration_minutes: 60,
        elapsed_minutes: 25,
        progress_percent: 42,
        estimated_maintenance_cost: 1800,
        estimated_downtime_cost: 42000,
        safety_status: "safe", // This active job CAN be evaluated for pre-emption!
        is_preempted: false,
        created_at: getSimulatedTimestamp(-35),
        updated_at: getSimulatedTimestamp(-5),
        description: "Emergency spindle bearing race replacement and precision runout calibration.",
      },
      {
        job_id: "JOB-102",
        machine_id: "M-03",
        machine_name: "Hydraulic Press 03",
        job_type: "corrective",
        priority: "critical",
        status: "in_progress",
        technician_id: "TECH-02",
        technician_name: "Elena Rostova",
        estimated_duration_minutes: 90,
        elapsed_minutes: 30,
        progress_percent: 33,
        estimated_maintenance_cost: 2400,
        estimated_downtime_cost: 48000,
        safety_status: "unsafe", // CANNOT be pre-empted because hydraulic accumulator is pressurized!
        is_preempted: false,
        created_at: getSimulatedTimestamp(-40),
        updated_at: getSimulatedTimestamp(-2),
        description: "Primary hydraulic pump cavitation rebuild and proportional valve replacement.",
      },
      {
        job_id: "JOB-103",
        machine_id: "M-14",
        machine_name: "Conveyor Drive 14",
        job_type: "preventive",
        priority: "medium",
        status: "assigned",
        technician_id: "TECH-05",
        technician_name: "Carlos Mendez",
        estimated_duration_minutes: 45,
        elapsed_minutes: 0,
        progress_percent: 0,
        estimated_maintenance_cost: 1200,
        estimated_downtime_cost: 26000,
        safety_status: "safe",
        created_at: getSimulatedTimestamp(-15),
        updated_at: getSimulatedTimestamp(-15),
        description: "Drive shaft coupling elastomeric insert replacement and laser dial alignment.",
      },
      {
        job_id: "JOB-104",
        machine_id: "M-11",
        machine_name: "Robotic Welder Cell 11",
        job_type: "preventive",
        priority: "high",
        status: "queued",
        technician_id: null,
        technician_name: null,
        estimated_duration_minutes: 50,
        elapsed_minutes: 0,
        progress_percent: 0,
        estimated_maintenance_cost: 1400,
        estimated_downtime_cost: 32000,
        safety_status: "safe",
        created_at: getSimulatedTimestamp(-10),
        updated_at: getSimulatedTimestamp(-10),
        description: "Inverter thermal dissipation heatsink cleanout and thermal grease reapplication.",
      },
      {
        job_id: "JOB-105",
        machine_id: "M-02",
        machine_name: "Stamping Press 02",
        job_type: "inspection",
        priority: "low",
        status: "queued",
        technician_id: null,
        technician_name: null,
        estimated_duration_minutes: 30,
        elapsed_minutes: 0,
        progress_percent: 0,
        estimated_maintenance_cost: 800,
        estimated_downtime_cost: 28000,
        safety_status: "safe",
        created_at: getSimulatedTimestamp(-5),
        updated_at: getSimulatedTimestamp(-5),
        description: "Die bolster tool clearance measurement and acoustic resonance check.",
      },
    ];

    // 4. Initialize Schedule (Contract Section 3.E)
    this.schedule = [
      {
        job_id: "JOB-101",
        machine_id: "M-07",
        technician_id: "TECH-01",
        technician_name: "Marcus Vance",
        planned_start_at: getSimulatedTimestamp(-30),
        planned_end_at: getSimulatedTimestamp(30),
        actual_start_at: getSimulatedTimestamp(-25),
        status: "in_progress",
        priority: "critical",
        job_type: "corrective",
        reason: "Cost-optimal dispatch: Mitigates $42,000 failure exposure",
      },
      {
        job_id: "JOB-102",
        machine_id: "M-03",
        technician_id: "TECH-02",
        technician_name: "Elena Rostova",
        planned_start_at: getSimulatedTimestamp(-35),
        planned_end_at: getSimulatedTimestamp(55),
        actual_start_at: getSimulatedTimestamp(-30),
        status: "in_progress",
        priority: "critical",
        job_type: "corrective",
        reason: "Highest expected loss on plant floor: $42,240 exposure",
      },
      {
        job_id: "JOB-103",
        machine_id: "M-14",
        technician_id: "TECH-05",
        technician_name: "Carlos Mendez",
        planned_start_at: getSimulatedTimestamp(15),
        planned_end_at: getSimulatedTimestamp(60),
        status: "planned",
        priority: "medium",
        job_type: "preventive",
        reason: "Preventive service window scheduled before line speed shift increase",
      },
      {
        job_id: "JOB-104",
        machine_id: "M-11",
        technician_id: "TECH-03",
        technician_name: "Devon Brooks",
        planned_start_at: getSimulatedTimestamp(65),
        planned_end_at: getSimulatedTimestamp(115),
        status: "planned",
        priority: "high",
        job_type: "preventive",
        reason: "Electrical specialist queued post-shift lunch window",
      },
    ];

    // 5. Initialize Events Audit Trail (Contract Section 3.G)
    this.events = [
      {
        id: "EVT-801",
        timestamp: getSimulatedTimestamp(-3),
        severity: "critical",
        category: "prediction",
        title: "Critical Telemetry Alert M-03",
        message: "Cavitation acoustic spectrum detected on Hydraulic Press 03 pump assembly. Probability escalated to 88%.",
        machine_id: "M-03",
        actor: "engine",
      },
      {
        id: "EVT-802",
        timestamp: getSimulatedTimestamp(-12),
        severity: "decision",
        category: "schedule",
        title: "Optimal Shift Schedule Generated",
        message: "Engine allocated 4 active slots balancing $1,800 dispatch cost against $114,000 total plant failure exposure.",
        actor: "orchestration",
      },
      {
        id: "EVT-803",
        timestamp: getSimulatedTimestamp(-25),
        severity: "info",
        category: "job",
        title: "Work Order JOB-101 Dispatched",
        message: "Marcus Vance assigned to CNC Milling Center 07 for corrective spindle bearing replacement.",
        machine_id: "M-07",
        job_id: "JOB-101",
        technician_id: "TECH-01",
        actor: "orchestration",
      },
      {
        id: "EVT-804",
        timestamp: getSimulatedTimestamp(-45),
        severity: "warning",
        category: "safety",
        title: "Hydraulic Circuit Lockout Required",
        message: "M-03 flagged as UNSAFE for interruption during accumulator bleed cycle.",
        machine_id: "M-03",
        actor: "engine",
      },
    ];
  }

  // -------------------------------------------------------------
  // Simulation Controls (Contract Section 3.A)
  // -------------------------------------------------------------
  public startSimulation(mode = "replay", speed = 1, scenario_id?: string) {
    this.state.status = "running";
    this.state.mode = mode as any;
    this.state.speed = speed;
    if (scenario_id) this.state.scenario_id = scenario_id;
    this.state.last_updated_at = new Date().toISOString();

    this.addEvent({
      severity: "info",
      category: "simulation",
      title: "Simulation Started",
      message: `Simulation engine initiated in '${mode}' mode at ${speed}x speed.`,
      actor: "operator",
    });

    return this.state;
  }

  public pauseSimulation() {
    this.state.status = "paused";
    this.state.last_updated_at = new Date().toISOString();

    this.addEvent({
      severity: "info",
      category: "simulation",
      title: "Simulation Paused",
      message: "Simulation clock and telemetry ingestion temporarily paused.",
      actor: "operator",
    });

    return this.state;
  }

  public resumeSimulation() {
    this.state.status = "running";
    this.state.last_updated_at = new Date().toISOString();

    this.addEvent({
      severity: "info",
      category: "simulation",
      title: "Simulation Resumed",
      message: "Real-time telemetry playback and decision cycle resumed.",
      actor: "operator",
    });

    return this.state;
  }

  public stepSimulation(steps = 1) {
    this.state.step_count = (this.state.step_count || 0) + steps;
    const now = new Date();
    now.setMinutes(now.getMinutes() + steps * 10);
    this.state.simulated_at = now.toISOString();
    this.state.last_updated_at = new Date().toISOString();

    // Advance jobs by steps * 5 mins
    this.jobs.forEach((j) => {
      if (j.status === "in_progress") {
        j.elapsed_minutes = Math.min(j.estimated_duration_minutes, j.elapsed_minutes + steps * 8);
        j.progress_percent = Math.min(100, Math.round((j.elapsed_minutes / j.estimated_duration_minutes) * 100));
        if (j.progress_percent >= 100) {
          j.status = "completed";
          // Free technician
          const tech = this.technicians.find((t) => t.technician_id === j.technician_id);
          if (tech) {
            tech.status = "available";
            tech.current_job_id = null;
            tech.current_job_name = null;
            tech.completed_jobs_count += 1;
          }
        }
      }
    });

    this.addEvent({
      severity: "info",
      category: "simulation",
      title: `Simulation Stepped (+${steps})`,
      message: `Simulation clock advanced by ${steps * 10} minutes. Work order progress updated.`,
      actor: "operator",
    });

    return this.state;
  }

  public resetSimulation() {
    this.initializeBaselineData();
    this.state.status = "running";
    this.state.simulated_at = getSimulatedTimestamp();
    this.state.last_updated_at = new Date().toISOString();
    this.state.step_count = 1;

    this.addEvent({
      severity: "info",
      category: "simulation",
      title: "Simulation Reset to Baseline",
      message: "All factory telemetry, machine health states, and schedule rosters restored to Detroit plant baseline.",
      actor: "operator",
    });

    return this.state;
  }

  public injectFailure(machine_id: string, scenario: string) {
    const target = this.machines.find((m) => m.machine_id === machine_id) ?? this.machines[0];
    target.status = "critical";
    target.failure_probability = 0.94;
    target.safety_status = scenario.includes("hydraulic") ? "unsafe" : "safe";
    target.decision = "urgent_maintenance";
    target.predicted_failure_mode =
      scenario === "bearing_seizure"
        ? "Catastrophic Spindle Bearing Seizure (Thermal Lock)"
        : scenario === "hydraulic_drop"
        ? "Hydraulic Line Pressure Rupture & Oil Loss"
        : "Catastrophic Vibration Breakdown (RMS > 5.8 mm/s)";
    target.telemetry.vibration = 5.92;
    target.telemetry.processTemp = 328.5;
    target.remaining_useful_life_hours = 6;

    // Create an incoming urgent job
    const newJobId = `JOB-URGENT-${Math.floor(100 + Math.random() * 900)}`;
    const newJob: JobContract = {
      job_id: newJobId,
      machine_id: target.machine_id,
      machine_name: target.name,
      job_type: "corrective",
      priority: "critical",
      status: "queued",
      technician_id: null,
      technician_name: null,
      estimated_duration_minutes: 75,
      elapsed_minutes: 0,
      progress_percent: 0,
      estimated_maintenance_cost: 2600,
      estimated_downtime_cost: target.failure_cost,
      safety_status: target.safety_status,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      description: `EMERGENCY DISPATCH: ${target.predicted_failure_mode}. Immediate technician allocation required to avoid $${(target.failure_cost / 1000).toFixed(0)}k line downtime.`,
    };

    this.jobs.unshift(newJob);

    this.addEvent({
      severity: "critical",
      category: "prediction",
      title: `FAILURE INJECTED: ${target.machine_id}`,
      message: `Simulated anomaly triggered on ${target.name}. Failure probability surged to 94%. Urgent job ${newJobId} queued for pre-emption review.`,
      machine_id: target.machine_id,
      job_id: newJobId,
      actor: "operator",
    });

    return { machine: target, job: newJob };
  }

  // -------------------------------------------------------------
  // Pre-emption Workflow (Contract Section 3.F)
  // -------------------------------------------------------------
  public evaluatePreemption(active_job_id: string, incoming_job_id: string): PreemptionEvaluationResponse {
    const currentJob = this.jobs.find((j) => j.job_id === active_job_id) ?? this.jobs[0];
    const incomingJob = this.jobs.find((j) => j.job_id === incoming_job_id) ?? this.jobs[1];

    const evalId = `EVAL-${Date.now()}`;

    // HARD SAFETY GATE (Contract Section 3.F & Section 5):
    // Safety status is a hard gate. Unsafe or indeterminate safety must NEVER be visually presented as safe or allowed!
    const isCurrentSafe = currentJob.safety_status === "safe";
    const isIncomingSafe = incomingJob.safety_status !== "unsafe";

    let decision: "allow" | "deny" | "needs_review" = "allow";
    let explanation = "";
    const reasonCodes: string[] = [];

    if (!isCurrentSafe) {
      decision = "deny";
      reasonCodes.push("SAFETY_HARD_GATE_ACTIVE_JOB_UNSAFE");
      explanation = `DENIED: Active job ${currentJob.job_id} on ${currentJob.machine_name} has safety status '${currentJob.safety_status.toUpperCase()}'. Interruption poses immediate physical hazard to technician or plant personnel. Work must complete before reassignment.`;
    } else if (currentJob.progress_percent >= 75) {
      decision = "deny";
      reasonCodes.push("ALMOST_COMPLETE_COST_INEFFICIENT");
      explanation = `DENIED: Active job is ${currentJob.progress_percent}% complete (${currentJob.elapsed_minutes}/${currentJob.estimated_duration_minutes} min). Interrupting now would incur higher restart tooling costs than completing the final 15 minutes.`;
    } else if (!isIncomingSafe) {
      decision = "needs_review";
      reasonCodes.push("INCOMING_SAFETY_INDETERMINATE");
      explanation = `NEEDS SAFETY REVIEW: Incoming job ${incomingJob.job_id} on ${incomingJob.machine_name} requires preliminary lockout/tagout sign-off before dispatch can commence.`;
    } else {
      decision = "allow";
      reasonCodes.push("ECONOMIC_SAVINGS_EXCEEDS_OVERHEAD", "SAFE_TOOLING_DISENGAGEMENT");
      explanation = `APPROVED FOR PRE-EMPTION: Active job ${currentJob.job_id} can be safely paused and tagged out. Expected downtime loss on incoming ${incomingJob.machine_name} ($${(incomingJob.estimated_downtime_cost / 1000).toFixed(0)}k) substantially outweighs the $450 interruption overhead.`;
    }

    const interruptionCost = decision === "allow" ? 450 : 2100;

    const alternatives: PreemptionEvaluationResponse["alternatives"] = [
      {
        action: "preempt",
        label: `Pre-empt ${currentJob.technician_name ?? "Technician"} immediately`,
        estimated_total_cost: incomingJob.estimated_maintenance_cost + interruptionCost,
        feasible: decision === "allow",
        reason: decision === "allow" ? "Lowest total shift cost; prevents catastrophic failure." : "Blocked by safety or tooling constraints.",
      },
      {
        action: "finish_current_job",
        label: `Let ${currentJob.technician_name ?? "Technician"} finish current job first (~${currentJob.estimated_duration_minutes - currentJob.elapsed_minutes}m)`,
        estimated_total_cost: Math.round(incomingJob.estimated_downtime_cost * 0.4) + incomingJob.estimated_maintenance_cost,
        feasible: true,
        reason: "Zero interruption penalty, but risks 25 minutes of high failure probability exposure.",
      },
      {
        action: "assign_other_technician",
        label: "Assign next available technician (Devon Brooks)",
        estimated_total_cost: incomingJob.estimated_maintenance_cost + 350,
        feasible: this.technicians.some((t) => t.status === "available"),
        reason: "Available technician exists with Level 2 mechanical certification.",
      },
      {
        action: "defer_incoming_job",
        label: "Defer incoming job to next shift window",
        estimated_total_cost: incomingJob.estimated_downtime_cost,
        feasible: false,
        reason: "Severe risk of catastrophic unscheduled line stoppage.",
      },
    ];

    const result: PreemptionEvaluationResponse = {
      evaluation_id: evalId,
      current_job: currentJob,
      incoming_job: incomingJob,
      decision,
      safe_to_interrupt: isCurrentSafe && decision === "allow",
      safety_status: currentJob.safety_status,
      reason_codes: reasonCodes,
      explanation,
      estimated_interruption_cost: interruptionCost,
      alternatives,
      evaluated_at: new Date().toISOString(),
    };

    this.evaluations.set(evalId, result);
    return result;
  }

  public executePreemption(evaluation_id: string, incoming_job_id: string, technician_id: string): PreemptionExecuteResponse {
    const evaluation = this.evaluations.get(evaluation_id);
    if (!evaluation) {
      throw new Error(`Evaluation ${evaluation_id} not found or expired.`);
    }

    if (evaluation.decision !== "allow") {
      throw new Error(`Cannot execute pre-emption: evaluation decision is '${evaluation.decision}'. Safety hard gate is closed.`);
    }

    const currentJob = this.jobs.find((j) => j.job_id === evaluation.current_job.job_id);
    const incomingJob = this.jobs.find((j) => j.job_id === incoming_job_id);
    const tech = this.technicians.find((t) => t.technician_id === technician_id);

    if (currentJob) {
      currentJob.status = "paused";
      currentJob.is_preempted = true;
      currentJob.preempted_reason = `Pre-empted by emergency dispatch of ${incomingJob?.machine_name ?? "incoming job"}`;
      currentJob.technician_id = null;
      currentJob.technician_name = null;
    }

    if (incomingJob) {
      incomingJob.status = "in_progress";
      incomingJob.technician_id = technician_id;
      incomingJob.technician_name = tech?.name ?? "Assigned Tech";
      incomingJob.elapsed_minutes = 5;
      incomingJob.progress_percent = 7;
    }

    if (tech) {
      tech.status = "on_job";
      tech.current_job_id = incoming_job_id;
      tech.current_job_name = incomingJob?.description.split(":")[0] ?? "Emergency Repair";
    }

    // Update schedule
    const nowIso = new Date().toISOString();
    const endIso = new Date(Date.now() + 75 * 60000).toISOString();
    this.schedule.unshift({
      job_id: incoming_job_id,
      machine_id: incomingJob?.machine_id ?? "M-03",
      technician_id,
      technician_name: tech?.name,
      planned_start_at: nowIso,
      planned_end_at: endIso,
      actual_start_at: nowIso,
      status: "in_progress",
      priority: "critical",
      job_type: "corrective",
      reason: `Pre-empted ${currentJob?.job_id} under approved evaluation ${evaluation_id}`,
    });

    this.addEvent({
      severity: "critical",
      category: "preemption",
      title: `PRE-EMPTION EXECUTED: ${technician_id} -> ${incoming_job_id}`,
      message: `${tech?.name ?? "Technician"} interrupted from ${currentJob?.job_id} and reassigned to emergency ${incoming_job_id} on ${incomingJob?.machine_name}. Previous job paused with progress preserved (${currentJob?.progress_percent}%).`,
      job_id: incoming_job_id,
      technician_id,
      actor: "operator",
    });

    return {
      success: true,
      message: `Pre-emption executed successfully. ${tech?.name} dispatched to ${incoming_job_id}.`,
      preempted_job_id: currentJob?.job_id ?? "",
      new_active_job_id: incoming_job_id,
      technician_id,
      timestamp: new Date().toISOString(),
    };
  }

  // -------------------------------------------------------------
  // Schedule & Replanning (Contract Section 3.E)
  // -------------------------------------------------------------
  public replanSchedule(request: ReplanRequest): ScheduleResponse {
    const activeJobs = this.jobs.filter((j) => j.status === "in_progress" || j.status === "queued" || j.status === "assigned");
    const availableTechs = this.technicians.filter((t) => t.status !== "unavailable");

    const newAssignments: ScheduleAssignment[] = [];
    const unassigned: string[] = [];

    let timeOffsetMinutes = 0;

    activeJobs.forEach((job, idx) => {
      const assignedTech = availableTechs[idx % availableTechs.length];
      if (assignedTech) {
        const start = getSimulatedTimestamp(timeOffsetMinutes);
        const end = getSimulatedTimestamp(timeOffsetMinutes + job.estimated_duration_minutes);
        newAssignments.push({
          job_id: job.job_id,
          machine_id: job.machine_id,
          technician_id: assignedTech.technician_id,
          technician_name: assignedTech.name,
          planned_start_at: start,
          planned_end_at: end,
          status: job.status === "in_progress" ? "in_progress" : "planned",
          priority: job.priority,
          job_type: job.job_type,
          reason: `Rebalanced shift schedule trigger: ${request.reason}`,
        });
        timeOffsetMinutes += 20;
      } else {
        unassigned.push(job.job_id);
      }
    });

    this.schedule = newAssignments;

    this.addEvent({
      severity: "info",
      category: "schedule",
      title: "Schedule Recalculated",
      message: `Shift planner recomputed ${newAssignments.length} work order assignments based on '${request.reason}'.`,
      actor: "engine",
    });

    return {
      generated_at: new Date().toISOString(),
      shift_name: "Shift A (Morning)",
      assignments: this.schedule,
      unassigned_job_ids: unassigned,
      conflicts: [],
    };
  }

  // -------------------------------------------------------------
  // Cost Analysis (Contract Section 3.H)
  // -------------------------------------------------------------
  public getCostAnalysis(): CostAnalysisResponse {
    return {
      currency: "USD",
      generated_at: new Date().toISOString(),
      options: [
        {
          option_id: "maintain_now",
          label: "Maintain Now (Recommended)",
          maintenance_cost: 1800,
          downtime_cost: 0,
          delay_risk_cost: 0,
          interruption_cost: 0,
          total_estimated_cost: 1800,
          feasible: true,
          assumptions: [
            "Technician dispatched within 15 minutes of initial vibration threshold exceedance.",
            "Zero unscheduled production line stoppage.",
            "Standard single-slot lockout-tagout procedure applied.",
          ],
        },
        {
          option_id: "delay_one_shift",
          label: "Delay 1 Shift (Next Window)",
          maintenance_cost: 2100,
          downtime_cost: 16000,
          delay_risk_cost: 22000,
          interruption_cost: 0,
          total_estimated_cost: 40100,
          feasible: true,
          assumptions: [
            "Machine continues operating in degraded state for 8 additional hours.",
            "Failure probability increases from 45% to 88%.",
            "Expected secondary collateral damage to spindle tooling and arbor.",
          ],
        },
        {
          option_id: "defer_weekend",
          label: "Defer to Weekend Planned Overtime",
          maintenance_cost: 3200,
          downtime_cost: 48000,
          delay_risk_cost: 38000,
          interruption_cost: 0,
          total_estimated_cost: 89200,
          feasible: false,
          assumptions: [
            "Requires 1.5× technician weekend overtime labor rates.",
            "High probability of catastrophic mid-week line breakdown before Saturday.",
            "Unmitigated production loss on critical path.",
          ],
        },
        {
          option_id: "emergency_interruption",
          label: "Emergency In-Shift Pre-emption",
          maintenance_cost: 2600,
          downtime_cost: 0,
          delay_risk_cost: 0,
          interruption_cost: 450,
          total_estimated_cost: 3050,
          feasible: true,
          assumptions: [
            "Safely interrupts active non-critical maintenance job.",
            "Includes $450 safe re-rigging and re-calibration overhead.",
            "Avoids $48,000 catastrophic failure on incoming priority asset.",
          ],
        },
      ],
      recommended_option_id: "maintain_now",
      explanation:
        "The economic optimization model demonstrates that immediate dispatch ($1,800) prevents $40,100 to $89,200 in catastrophic downtime exposure. If technician capacity is blocked, emergency pre-emption ($3,050 total cost) is the next most cost-efficient feasible alternative.",
      parameters: {
        inspection_dispatch_fee: 1800,
        alert_review_overhead: 260,
        hourly_downtime_cost: 12000,
        technician_rate: 85,
      },
    };
  }

  // -------------------------------------------------------------
  // Event Log helper
  // -------------------------------------------------------------
  public addEvent(event: Omit<AuditTrailEvent, "id" | "timestamp">) {
    const fullEvent: AuditTrailEvent = {
      ...event,
      id: generateId("EVT"),
      timestamp: new Date().toISOString(),
    };
    this.events.unshift(fullEvent);
    if (this.events.length > 100) {
      this.events = this.events.slice(0, 100);
    }
    return fullEvent;
  }
}

export const simulationStore = SimulationStore.getInstance();
