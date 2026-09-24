export async function GET(request: Request, context: { params: Promise<{ filename: string }> }) {
  const { filename } = await context.params;
  if (!filename || filename.startsWith('.') || /[/\\\x00-\x1f]/.test(filename) || !filename.endsWith('.pdf')) {
    return Response.json({ detail: '无效的 PDF 文件名。' }, { status: 400 });
  }
  try {
    const origin = (process.env.RAG_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const response = await fetch(`${origin}/documents/${encodeURIComponent(filename)}/file`, {
      cache: 'no-store', signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]),
    });
    if (!response.ok) {
      const data = await response.json();
      return Response.json(data, { status: response.status, headers: { 'Cache-Control': 'no-store' } });
    }
    if (!response.headers.get('content-type')?.startsWith('application/pdf')) {
      await response.body?.cancel();
      return Response.json({ detail: '服务未返回 PDF。' }, { status: 502 });
    }
    const headers = new Headers({ 'Content-Type': 'application/pdf', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const name of ['content-length', 'content-disposition']) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(response.body, { status: 200, headers });
  } catch {
    return Response.json({ detail: '无法读取 PDF，请稍后重试。' }, { status: 502 });
  }
}
