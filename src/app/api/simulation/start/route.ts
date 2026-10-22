import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const state = simulationStore.startSimulation(body.mode, body.speed, body.scenario_id);
  return successResponse(state);
}
