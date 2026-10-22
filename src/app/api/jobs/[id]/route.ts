import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse, errorResponse } from "@/lib/api-response";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const job = simulationStore.jobs.find(
    (j) => j.job_id.toLowerCase() === id.toLowerCase()
  );

  if (!job) {
    return errorResponse("NOT_FOUND", `Job ${id} not found`, undefined, 404);
  }

  return successResponse(job);
}
