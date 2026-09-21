export class BodyError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

// Bound the bytes before JSON/multipart parsing, including chunked requests.
export async function limitedBody(request: Request, limit: number): Promise<ArrayBuffer> {
  const length = request.headers.get('content-length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > limit)) {
    throw new BodyError('请求内容过大或长度无效。', 413);
  }
  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  const parts: Uint8Array[] = [];
  let size = 0;
  let timer: ReturnType<typeof setTimeout>;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new BodyError('上传超时，请重试。', 408)), 30000);
  });
  try {
    while (true) {
      const { value, done } = await Promise.race([reader.read(), deadline]);
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new BodyError('请求内容过大。', 413);
      parts.push(value);
    }
    const result = new Uint8Array(size);
    let offset = 0;
    for (const part of parts) { result.set(part, offset); offset += part.byteLength; }
    return result.buffer;
  } catch (error) {
    void reader.cancel().catch(() => {});
    throw error;
  } finally { clearTimeout(timer!); }
}
