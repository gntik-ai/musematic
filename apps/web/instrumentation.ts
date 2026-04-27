import { log, registerClientErrorHandlers } from "@/lib/logging";

export async function register() {
  log.info("web.instrumentation.started");
}

export { registerClientErrorHandlers };
