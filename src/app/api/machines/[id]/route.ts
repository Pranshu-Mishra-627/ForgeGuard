import { NextRequest } from "next/server";
import { simulationStore } from "@/lib/simulation-store";
import { successResponse, errorResponse } from "@/lib/api-response";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const machine = simulationStore.machines.find(
    (m) => m.machine_id.toLowerCase() === id.toLowerCase()
  );

  if (!machine) {
    return errorResponse("NOT_FOUND", `Machine ${id} not found`, undefined, 404);
  }

  return successResponse(machine);
}
