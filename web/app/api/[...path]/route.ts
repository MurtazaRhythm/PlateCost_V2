export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API_ORIGIN = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context) {
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const destination = `${API_ORIGIN}/api/${path.join("/")}${incoming.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  try {
    const upstream = await fetch(destination, init);
    const outgoing = new Headers(upstream.headers);
    outgoing.delete("content-encoding");
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return Response.json({ detail: "PlateCost can't reach the server." }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
