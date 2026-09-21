import { backend } from '../../../lib/backend';
export async function POST(request: Request) {
  let body;
  try { body = await request.json(); }
  catch { return Response.json({ detail: '请求必须是 JSON。' }, { status: 400 }); }
  return backend('/ask', body);
}
