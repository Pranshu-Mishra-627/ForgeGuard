import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse } from "@/lib/api-response";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const severity = searchParams.get("severity");
  const category = searchParams.get("category");
  const machine_id = searchParams.get("machine_id");

  let events = simulationStore.events;

  if (severity && severity !== "all") {
    events = events.filter((e) => e.severity === severity);
  }
  if (category && category !== "all") {
    events = events.filter((e) => e.category === category);
  }
  if (machine_id) {
    events = events.filter((e) => e.machine_id === machine_id);
  }

  return successResponse(events);
}
