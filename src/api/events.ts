import { apiClient } from "./client";
import { AuditTrailEvent } from "@/types/api";

export interface EventsQuery {
  severity?: string;
  category?: string;
  machine_id?: string;
}

export const eventsApi = {
  getAll: (query?: EventsQuery) => {
    const params = new URLSearchParams();
    if (query?.severity) params.set("severity", query.severity);
    if (query?.category) params.set("category", query.category);
    if (query?.machine_id) params.set("machine_id", query.machine_id);
    const qs = params.toString();
    return apiClient.get<AuditTrailEvent[]>(`/events${qs ? `?${qs}` : ""}`);
  },
};
