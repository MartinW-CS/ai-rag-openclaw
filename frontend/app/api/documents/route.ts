import { forward } from '../../../lib/backend';
export async function GET() { return forward('/documents'); }
export async function POST(request: Request) {
  try {
    const data = await request.formData();
    const file = data.get('file');
    if (!(file instanceof File)) return Response.json({ detail: '请选择 PDF。' }, { status: 400 });
    if (file.size > 10 * 1024 * 1024) return Response.json({ detail: 'PDF 不能超过 10 MB。' }, { status: 413 });
    return forward('/documents', { method: 'POST', body: data });
  } catch { return Response.json({ detail: '无法读取上传文件。' }, { status: 400 }); }
}
export async function DELETE(request: Request) {
  const filename = new URL(request.url).searchParams.get('filename');
  if (!filename) return Response.json({ detail: '缺少文件名。' }, { status: 400 });
  return forward(`/documents?filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
}
