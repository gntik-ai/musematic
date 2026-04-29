import { NextResponse, type NextRequest } from "next/server";

const grafanaBaseUrl =
  process.env.GRAFANA_INTERNAL_URL ?? "http://grafana.platform-observability.svc.cluster.local";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const target = new URL(path.join("/"), grafanaBaseUrl);
  target.search = request.nextUrl.search;

  const response = await fetch(target, {
    headers: {
      cookie: request.headers.get("cookie") ?? "",
      authorization: request.headers.get("authorization") ?? "",
    },
    cache: "no-store",
  });

  const body = await response.arrayBuffer();
  const proxied = new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "text/html; charset=utf-8",
      "Content-Security-Policy": "frame-ancestors 'self'",
    },
  });
  return proxied;
}
