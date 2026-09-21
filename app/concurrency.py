"""Reject overload before parsing bodies; bound synchronous work even after timeout."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from starlette.responses import JSONResponse


class Busy(Exception):
    pass


class BoundedExecutor:
    def __init__(self, workers):
        self.slots = BoundedSemaphore(workers)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='rag-retrieval')

    async def run(self, function, *args):
        if not self.slots.acquire(blocking=False):
            raise Busy('检索繁忙，请稍后重试。')
        try:
            future = self.executor.submit(function, *args)
        except BaseException:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: self.slots.release())
        # Cancelling the caller cannot free a slot while CPU work is still running.
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda result: None if result.cancelled() else result.exception())
        return await asyncio.shield(wrapped)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


class AdmissionMiddleware:
    def __init__(self, app, ask_limit=8, upload_limit=2):
        self.app = app
        self.ask_slots = BoundedSemaphore(ask_limit)
        self.upload_slots = BoundedSemaphore(upload_limit)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope['path'], scope['method']
        upload = path == '/documents' and method == 'POST'
        asking = path == '/ask' and method == 'POST'
        slots = self.upload_slots if upload else self.ask_slots if asking else None
        if slots is None:
            return await self.app(scope, receive, send)
        if not slots.acquire(blocking=False):
            return await JSONResponse({'detail': '服务繁忙，请稍后重试。'}, status_code=429,
                                      headers={'Retry-After': '2'})(scope, receive, send)
        try:
            limit = 11 * 1024 * 1024 if upload else 32 * 1024
            headers = dict(scope['headers'])
            if b'content-length' in headers:
                try:
                    size = int(headers[b'content-length'])
                    if size < 0:
                        raise ValueError()
                except ValueError:
                    return await JSONResponse({'detail': '无效的请求长度。'}, status_code=400)(scope, receive, send)
                if size > limit:
                    return await JSONResponse({'detail': '请求内容过大。'}, status_code=413)(scope, receive, send)
            parts, size = [], 0
            try:
                async with asyncio.timeout(30):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return
                        body = message.get('body', b'')
                        size += len(body)
                        if size > limit:
                            return await JSONResponse({'detail': '请求内容过大。'}, status_code=413)(scope, receive, send)
                        parts.append(body)
                        if not message.get('more_body', False):
                            break
            except TimeoutError:
                return await JSONResponse({'detail': '接收请求超时。'}, status_code=408)(scope, receive, send)
            body = b''.join(parts)
            parts.clear()
            delivered = False

            async def replay():
                nonlocal delivered, body
                if not delivered:
                    delivered = True
                    result = {'type': 'http.request', 'body': body, 'more_body': False}
                    body = b''
                    return result
                return await receive()

            await self.app(scope, replay, send)
        finally:
            slots.release()
