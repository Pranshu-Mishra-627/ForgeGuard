import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse, errorResponse } from "@/lib/api-response";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));

  if (!body.evaluation_id || !body.incoming_job_id || !body.technician_id) {
    return errorResponse(
      "INVALID_REQUEST",
      "evaluation_id, incoming_job_id, and technician_id are required"
    );
  }

  try {
    const result = simulationStore.executePreemption(
      body.evaluation_id,
      body.incoming_job_id,
      body.technician_id
    );
    return successResponse(result);
  } catch (err: any) {
    return errorResponse("PREEMPTION_EXECUTION_DENIED", err?.message ?? "Execution denied", undefined, 403);
  }
}
