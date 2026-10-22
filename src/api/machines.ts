import { apiClient } from "./client";
import { MachineContract } from "@/types/api";

export const machinesApi = {
  getAll: () => apiClient.get<MachineContract[]>("/machines"),
  getById: (id: string) => apiClient.get<MachineContract>(`/machines/${id}`),
};
