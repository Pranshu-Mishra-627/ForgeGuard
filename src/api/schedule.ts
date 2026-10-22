import { apiClient } from "./client";
import { ScheduleResponse, ReplanRequest } from "@/types/api";

export const scheduleApi = {
  get: () => apiClient.get<ScheduleResponse>("/schedule"),

  replan: (params: ReplanRequest) =>
    apiClient.post<ScheduleResponse>("/schedule/replan", params),
};
