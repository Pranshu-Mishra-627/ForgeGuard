import { Machine, ShiftPlanResult, ThresholdCostPoint } from "./types";

export const INSPECTION_COST = 1800; // $1.8k per scheduled technician dispatch
export const ALERT_REVIEW_COST = 260; // $260 review cost per alert

export function planShift(
  machines: Machine[],
  slots: number,
  threshold: number,
  pinnedIds: string[] = []
): ShiftPlanResult {
  const pinnedSet = new Set(pinnedIds);

  // Filter alerted or pinned machines
  const alerted = machines.filter(
    (m) => m.probability >= threshold || pinnedSet.has(m.id)
  );

  // Priority ranking: pinned first, then descending priority score, tie-break by ascending machine id
  const ranked = [...alerted].sort((a, b) => {
    const aPin = pinnedSet.has(a.id) ? 1 : 0;
    const bPin = pinnedSet.has(b.id) ? 1 : 0;
    if (aPin !== bPin) return bPin - aPin;
    if (b.priority !== a.priority) return b.priority - a.priority;
    return a.id.localeCompare(b.id);
  });

  const scheduled = ranked.slice(0, slots);
  const deferred = ranked.slice(slots);

  const statusById = new Map<string, "scheduled" | "deferred">();
  const reasonsById = new Map<string, string>();

  scheduled.forEach((m, idx) => {
    statusById.set(m.id, "scheduled");
    const isPin = pinnedSet.has(m.id);
    const reason = isPin
      ? `Manual override: Pinned by supervisor to slot #${idx + 1}; expedited service scheduled.`
      : `Selected for service: Alert triggered (${(m.probability * 100).toFixed(1)}% ≥ ${(
          threshold * 100
        ).toFixed(0)}%); assigned slot #${idx + 1} of ${slots} (priority score ${m.priority}).`;
    reasonsById.set(m.id, reason);
  });

  deferred.forEach((m, idx) => {
    statusById.set(m.id, "deferred");
    const reason =
      slots === 0
        ? `Deferred: Alert triggered (${(m.probability * 100).toFixed(1)}% ≥ ${(
            threshold * 100
          ).toFixed(0)}%), but zero technician slots are available.`
        : `Deferred: Alert triggered (priority score ${m.priority}, queue rank #${
            slots + idx + 1
          }), but capacity limit reached (${slots} slots assigned to higher-priority machines).`;
    reasonsById.set(m.id, reason);
  });

  // Calculate exposures
  const totalExposure = machines
    .filter((m) => m.probability >= threshold)
    .reduce((sum, m) => sum + m.probability * m.failureCost, 0);

  const avoidedExposure = scheduled.reduce(
    (sum, m) => sum + m.probability * m.failureCost,
    0
  );

  const unmitigatedExposure = deferred.reduce(
    (sum, m) => sum + m.probability * m.failureCost,
    0
  );

  return {
    ranked,
    scheduled,
    deferred,
    statusById,
    reasonsById,
    totalExposure,
    avoidedExposure,
    unmitigatedExposure,
  };
}

export function generateCostCurve(
  machines: Machine[],
  slots: number,
  inspectionCost: number = INSPECTION_COST,
  alertReviewCost: number = ALERT_REVIEW_COST
): ThresholdCostPoint[] {
  // Candidate thresholds: 5% to 95% in step 5% (19 points)
  const thresholds = [
    0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65,
    0.7, 0.75, 0.8, 0.85, 0.9, 0.95,
  ];

  return thresholds.map((t) => {
    const plan = planShift(machines, slots, t);

    // Unscheduled / deferred machines above threshold still contribute to failure exposure
    const unmitigatedFailure = plan.unmitigatedExposure;
    // Sub-threshold machines with latent probability contribute background risk
    const latentFailure = machines
      .filter((m) => m.probability < t)
      .reduce((sum, m) => sum + m.probability * m.failureCost * 0.85, 0);

    const failureCost = Math.round(unmitigatedFailure + latentFailure);

    // Maintenance cost: scheduled technician dispatches + review cost for all alerts
    const alertCount = plan.ranked.length;
    const maintenanceCost = Math.round(
      plan.scheduled.length * inspectionCost + alertCount * alertReviewCost
    );

    const totalCost = failureCost + maintenanceCost;

    return {
      threshold: t,
      cost: totalCost,
      failureCost,
      maintenanceCost,
      tp: plan.scheduled.filter((m) => m.probability >= 0.5).length,
      fp: plan.scheduled.filter((m) => m.probability < 0.5).length,
      fn: plan.deferred.filter((m) => m.probability >= 0.5).length,
      tn: machines.filter((m) => m.probability < t && m.probability < 0.5).length,
    };
  });
}

export function findOptimalThreshold(curve: ThresholdCostPoint[]): ThresholdCostPoint {
  if (curve.length === 0) {
    return {
      threshold: 0.4,
      cost: 0,
      failureCost: 0,
      maintenanceCost: 0,
      tp: 0,
      fp: 0,
      fn: 0,
      tn: 0,
    };
  }
  // Tie-breaking: pick highest threshold among identical minimum cost
  return curve.reduce((best, curr) => {
    if (curr.cost < best.cost) return curr;
    if (curr.cost === best.cost && curr.threshold > best.threshold) return curr;
    return best;
  }, curve[0]);
}
