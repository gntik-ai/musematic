import { z } from "zod";

export const LogLevelSchema = z.enum(["debug", "info", "warn", "error", "fatal"]);

export const LogEventSchema = z.object({
  timestamp: z.string().datetime(),
  level: LogLevelSchema,
  service: z.literal("web").default("web"),
  bounded_context: z.literal("frontend").default("frontend"),
  message: z.string().min(1),
  trace_id: z.string().optional(),
  span_id: z.string().optional(),
  correlation_id: z.string().optional(),
  workspace_id: z.string().optional(),
  goal_id: z.string().optional(),
  user_id: z.string().optional(),
  execution_id: z.string().optional(),
  url: z.string().optional(),
  user_agent: z.string().optional(),
  stack: z.string().optional(),
});

export type LogLevel = z.infer<typeof LogLevelSchema>;
export type LogEvent = z.infer<typeof LogEventSchema>;
export type LogFields = Partial<Omit<LogEvent, "timestamp" | "level" | "service" | "bounded_context" | "message">>;

function buildEvent(level: LogLevel, message: string, fields: LogFields = {}): LogEvent {
  return LogEventSchema.parse({
    timestamp: new Date().toISOString(),
    level,
    service: "web",
    bounded_context: "frontend",
    message,
    ...fields,
  });
}

function emit(level: LogLevel, message: string, fields?: LogFields): void {
  const event = buildEvent(level, message, fields);
  if (typeof window === "undefined") {
    console.log(JSON.stringify(event));
    return;
  }
  const clientEvent: LogEvent = {
    ...event,
    url: event.url ?? window.location.href,
    user_agent: event.user_agent ?? window.navigator.userAgent,
  };
  void fetch("/api/log/client-error", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(clientEvent),
    keepalive: true,
  }).catch(() => undefined);
}

export const log = {
  debug(message: string, fields?: LogFields): void {
    emit("debug", message, fields);
  },
  info(message: string, fields?: LogFields): void {
    emit("info", message, fields);
  },
  warn(message: string, fields?: LogFields): void {
    emit("warn", message, fields);
  },
  error(message: string, fields?: LogFields): void {
    emit("error", message, fields);
  },
  fatal(message: string, fields?: LogFields): void {
    emit("fatal", message, fields);
  },
};

export function registerClientErrorHandlers(): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }
  const onError = (event: ErrorEvent) => {
    const fields: LogFields = {
      url: window.location.href,
      user_agent: window.navigator.userAgent,
    };
    if (event.error instanceof Error && event.error.stack) {
      fields.stack = event.error.stack;
    }
    log.error(event.message || "client.error", fields);
  };
  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const fields: LogFields = {
      url: window.location.href,
      user_agent: window.navigator.userAgent,
    };
    if (reason instanceof Error && reason.stack) {
      fields.stack = reason.stack;
    } else if (reason !== undefined && reason !== null) {
      fields.stack = String(reason);
    }
    log.error(reason instanceof Error ? reason.message : "client.unhandled_rejection", fields);
  };
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onUnhandledRejection);
  return () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onUnhandledRejection);
  };
}
