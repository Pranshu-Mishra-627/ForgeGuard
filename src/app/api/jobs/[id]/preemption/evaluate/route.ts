import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse, errorResponse } from "@/lib/api-response";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));

  if (!body.incoming_job_id) {
    return errorResponse("INVALID_REQUEST", "incoming_job_id is required");
  }

  try {
    const evaluation = simulationStore.evaluatePreemption(id, body.incoming_job_id);
    return successResponse(evaluation);
  } catch (err: any) {
    return errorResponse("PREEMPTION_ERROR", err?.message ?? "Failed to evaluate preemption");
  }
}
