import { forward } from '../../../lib/backend';
import { BodyError, limitedBody } from '../../../lib/request-body';
let uploads = 0;
export async function GET() { return forward('/documents'); }
export async function POST(request: Request) {
  if (uploads >= 2) return Response.json({ detail: '上传繁忙，请稍后重试。' }, { status: 429, headers: { 'Retry-After': '2' } });
  uploads++;
  try {
    const body = await limitedBody(request, 11 * 1024 * 1024);
    const data = await new Request(request.url, { method: 'POST', headers: { 'Content-Type': request.headers.get('content-type') || '' }, body }).formData();
    const file = data.get('file');
    if (!(file instanceof File)) return Response.json({ detail: '请选择 PDF。' }, { status: 400 });
    if (file.size > 10 * 1024 * 1024) return Response.json({ detail: 'PDF 不能超过 10 MB。' }, { status: 413 });
    return await forward('/documents', { method: 'POST', body: data, signal: request.signal });
  } catch (error) {
    return Response.json({ detail: error instanceof BodyError ? error.message : '无法读取上传文件。' }, { status: error instanceof BodyError ? error.status : 400 });
  } finally { uploads--; }
}
export async function DELETE(request: Request) {
  const filename = new URL(request.url).searchParams.get('filename');
  if (!filename) return Response.json({ detail: '缺少文件名。' }, { status: 400 });
  return forward(`/documents?filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
}
