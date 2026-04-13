export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
  [key: string]: unknown;
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details: ApiErrorDetail[] | undefined;
  public readonly meta: Record<string, unknown> | undefined;

  constructor(
    code: string,
    message: string,
    status: number,
    details?: ApiErrorDetail[],
    meta?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.meta = meta;
  }
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
  hasPrev: boolean;
}

export interface CursorPaginatedResponse<T> {
  items: T[];
  nextCursor: string | null;
  prevCursor: string | null;
  total: number;
}

export interface ApiRequestOptions extends RequestInit {
  skipAuth?: boolean;
  skipRetry?: boolean;
}
