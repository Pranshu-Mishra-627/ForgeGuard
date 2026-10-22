import { apiClient } from "./client";
import { TechnicianContract } from "@/types/api";

export const techniciansApi = {
  getAll: () => apiClient.get<TechnicianContract[]>("/technicians"),
};
