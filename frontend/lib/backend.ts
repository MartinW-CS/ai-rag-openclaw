// Only the Next.js server reads this address; no credentials reach the browser.
export async function forward(path: string, init: RequestInit = {}) {
  try {
    const response = await fetch(`${(process.env.RAG_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')}${path}`, {
      ...init, cache: 'no-store', signal: AbortSignal.timeout(path === '/health' ? 5000 : 180000),
    });
    return Response.json(await response.json(), { status: response.status });
  } catch {
    return Response.json({ detail: '无法连接服务，或请求已超时。请确认后端正在运行后重试。' }, { status: 502 });
  }
}
export async function backend(path: '/health' | '/ask', body?: unknown) {
  return forward(path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}
