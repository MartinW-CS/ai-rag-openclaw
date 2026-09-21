import { backend } from '../../../lib/backend';
import { BodyError, limitedBody } from '../../../lib/request-body';
let active = 0;
export async function POST(request: Request) {
  if (active >= 8) return Response.json({ detail: '问答繁忙，请稍后重试。' }, { status: 429, headers: { 'Retry-After': '2' } });
  active++;
  try {
    const body = JSON.parse(new TextDecoder().decode(await limitedBody(request, 32 * 1024)));
    return await backend('/ask', body, request.signal);
  } catch (error) {
    return Response.json({ detail: error instanceof BodyError ? error.message : '请求必须是有效 JSON。' }, { status: error instanceof BodyError ? error.status : 400 });
  } finally { active--; }
}
