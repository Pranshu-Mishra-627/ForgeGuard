import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function GET() {
  const costAnalysis = simulationStore.getCostAnalysis();
  return successResponse(costAnalysis);
}
