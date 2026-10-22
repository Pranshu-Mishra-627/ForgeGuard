import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function GET() {
  return successResponse(simulationStore.jobs);
}
