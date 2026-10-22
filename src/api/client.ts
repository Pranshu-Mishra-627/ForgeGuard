import { ApiResponse, ApiError } from "@/types/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

export class ApiClientError extends Error {
  public code: string;
  public details?: unknown;
  public requestId?: string;

  constructor(message: string, code = "UNKNOWN_ERROR", details?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 12000);

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const json = await res.json().catch(() => null);

    if (!res.ok) {
      const errorPayload = json as ApiError | null;
      throw new ApiClientError(
        errorPayload?.error?.message || `Request failed with status ${res.status}`,
        errorPayload?.error?.code || `HTTP_${res.status}`,
        errorPayload?.error?.details,
        errorPayload?.request_id
      );
    }

    // Unpack data wrapper if present
    if (json && typeof json === "object" && "data" in json) {
      return (json as ApiResponse<T>).data;
    }

    return json as T;
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err?.name === "AbortError") {
      throw new ApiClientError("Request timed out after 12 seconds", "TIMEOUT");
    }
    if (err instanceof ApiClientError) {
      throw err;
    }
    throw new ApiClientError(err?.message || "Network request failed", "NETWORK_ERROR");
  }
}

export const apiClient = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: "GET" }),
  post: <T>(endpoint: string, body?: unknown) =>
    request<T>(endpoint, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
};
