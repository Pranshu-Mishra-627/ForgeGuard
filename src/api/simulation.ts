import { apiClient } from "./client";
import {
  SimulationState,
  SimulationStartRequest,
  SimulationStepRequest,
  SimulationInjectFailureRequest,
  MachineContract,
  JobContract,
} from "@/types/api";

export const simulationApi = {
  getState: () => apiClient.get<SimulationState>("/simulation/state"),

  start: (params: SimulationStartRequest) =>
    apiClient.post<SimulationState>("/simulation/start", params),

  pause: () => apiClient.post<SimulationState>("/simulation/pause"),

  resume: () => apiClient.post<SimulationState>("/simulation/resume"),

  step: (params?: SimulationStepRequest) =>
    apiClient.post<SimulationState>("/simulation/step", params ?? { steps: 1 }),

  reset: () => apiClient.post<SimulationState>("/simulation/reset"),

  injectFailure: (params: SimulationInjectFailureRequest) =>
    apiClient.post<{ machine: MachineContract; job: JobContract }>("/simulation/inject-failure", params),
};
