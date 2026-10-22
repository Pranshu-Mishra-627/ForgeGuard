import { NextResponse } from "next/server";

export function successResponse<T>(data: T, status = 200) {
  return NextResponse.json(
    {
      data,
      request_id: `req_${Math.random().toString(36).substring(2, 10)}`,
    },
    { status }
  );
}

export function errorResponse(code: string, message: string, details?: unknown, status = 400) {
  return NextResponse.json(
    {
      error: {
        code,
        message,
        details,
      },
      request_id: `req_${Math.random().toString(36).substring(2, 10)}`,
    },
    { status }
  );
}
