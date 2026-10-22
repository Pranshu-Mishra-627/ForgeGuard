import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function POST() {
  const state = simulationStore.resumeSimulation();
  return successResponse(state);
}
