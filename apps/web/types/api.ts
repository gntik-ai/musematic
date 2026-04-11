export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details?: ApiErrorDetail[];

  constructor(code: string, message: string, status: number, details?: ApiErrorDetail[]) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
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
