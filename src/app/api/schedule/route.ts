import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function GET() {
  const scheduleData = {
    generated_at: new Date().toISOString(),
    shift_name: "Shift A (Morning)",
    assignments: simulationStore.schedule,
    unassigned_job_ids: simulationStore.jobs.filter((j) => j.status === "queued").map((j) => j.job_id),
    conflicts: [],
  };
  return successResponse(scheduleData);
}
