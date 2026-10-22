import { apiClient } from "./client";
import {
  JobContract,
  PreemptionEvaluationRequest,
  PreemptionEvaluationResponse,
  PreemptionExecuteRequest,
  PreemptionExecuteResponse,
} from "@/types/api";

export const jobsApi = {
  getAll: () => apiClient.get<JobContract[]>("/jobs"),
  getById: (id: string) => apiClient.get<JobContract>(`/jobs/${id}`),

  evaluatePreemption: (activeJobId: string, params: PreemptionEvaluationRequest) =>
    apiClient.post<PreemptionEvaluationResponse>(`/jobs/${activeJobId}/preemption/evaluate`, params),

  executePreemption: (activeJobId: string, params: PreemptionExecuteRequest) =>
    apiClient.post<PreemptionExecuteResponse>(`/jobs/${activeJobId}/preemption/execute`, params),
};
