import { apiClient } from "./client";
import { CostAnalysisResponse } from "@/types/api";

export const costAnalysisApi = {
  get: () => apiClient.get<CostAnalysisResponse>("/cost-analysis"),
};
