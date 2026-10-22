import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const state = simulationStore.stepSimulation(body.steps ?? 1);
  return successResponse(state);
}
