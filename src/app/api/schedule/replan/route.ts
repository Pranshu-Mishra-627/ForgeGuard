import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const replanned = simulationStore.replanSchedule({
    reason: body.reason ?? "new_critical_job",
    trigger_job_id: body.trigger_job_id,
  });
  return successResponse(replanned);
}
