import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse, errorResponse } from "@/lib/api-response";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  if (!body.machine_id) {
    return errorResponse("INVALID_REQUEST", "machine_id is required");
  }

  const result = simulationStore.injectFailure(
    body.machine_id,
    body.scenario ?? "bearing_seizure"
  );

  return successResponse(result);
}
