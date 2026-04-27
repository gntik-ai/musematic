import { LogEventSchema } from "@/lib/logging";
import { NextRequest, NextResponse } from "next/server";

const WINDOW_MS = 60_000;
const MAX_EVENTS_PER_WINDOW = 60;
const buckets = new Map<string, { count: number; resetAt: number }>();

function clientKey(request: NextRequest): string {
  return (
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip") ||
    "unknown"
  );
}

function isRateLimited(key: string, now: number): boolean {
  const bucket = buckets.get(key);
  if (!bucket || bucket.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + WINDOW_MS });
    return false;
  }
  bucket.count += 1;
  return bucket.count > MAX_EVENTS_PER_WINDOW;
}

export async function POST(request: NextRequest) {
  const key = clientKey(request);
  if (isRateLimited(key, Date.now())) {
    return NextResponse.json({ error: "rate_limited" }, { status: 429 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const parsed = LogEventSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_log_event" }, { status: 400 });
  }

  console.log(JSON.stringify(parsed.data));
  return new NextResponse(null, { status: 204 });
}
