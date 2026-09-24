import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import unittest
from unittest.mock import AsyncMock

from support import ApiFixture, FakeIndex


class ConcurrencyTests(ApiFixture, unittest.TestCase):
    def test_admission_rejects_overload_and_health_stays_live(self):
        entered, release = Event(), Event()
        counter, lock = [0], Lock()
        async def slow_generator(question, chunks):
            with lock:
                counter[0] += 1
                if counter[0] == 2:
                    entered.set()
            await asyncio.to_thread(release.wait, 5)
            return 'Answer'
        self.setup_api(generator=slow_generator, ask_limit=2)
        self.upload(); self.ready()
        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [callers.submit(self.client.post, '/ask', json={'question': 'Q'}) for _ in range(2)]
            try:
                self.assertTrue(entered.wait(3))
                response = self.client.post('/ask', json={'question': 'Q'})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers['retry-after'], '2')
                self.assertEqual(self.client.get('/health').status_code, 200)
            finally:
                release.set()
            self.assertTrue(all(f.result().status_code == 200 for f in futures))
        self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 200)

    def test_timeout_cancels_generation_and_releases_admission(self):
        cancelled = Event()
        async def never(question, chunks):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        self.setup_api(generator=never, ask_limit=1, ask_timeout=0.05)
        self.upload(); self.ready()
        self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 504)
        self.assertTrue(cancelled.is_set())
        self.app.state.generator = AsyncMock(return_value='Answer')
        self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 200)

    def test_timed_out_cpu_work_keeps_its_slot(self):
        entered, release = Event(), Event()
        class SlowIndex(FakeIndex):
            def retrieve(self, question, allowed, top_k=4):
                entered.set(); release.wait(5)
                return super().retrieve(question, allowed, top_k)
        self.setup_api(builder=SlowIndex, retrieval_workers=1, ask_timeout=0.1)
        self.upload(); self.ready()
        try:
            self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 504)
            self.assertTrue(entered.is_set())
            self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 429)
            self.assertEqual(self.client.get('/health').status_code, 200)
        finally:
            release.set()

    def test_update_coalescing_old_index_queries_and_deleted_source_filter(self):
        building, release = Event(), Event()
        versions = []
        def builder(directory):
            index = FakeIndex(directory)
            versions.append(index)
            if len(versions) == 2:
                building.set(); release.wait(5)
            return index
        self.setup_api(builder=builder)
        self.upload('a.pdf'); self.ready()
        old = self.service.current
        try:
            self.upload('b.pdf')
            self.assertTrue(building.wait(3))
            self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).json()['sources'], [{'source': 'a.pdf', 'page': 1}])
            for name in ('c.pdf', 'd.pdf'):
                self.upload(name)
            self.client.delete('/documents', params={'filename': 'a.pdf'})
            self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 503)
        finally:
            release.set()
        self.ready()
        self.assertEqual(len(versions), 3)  # one active build plus one coalesced update
        self.assertTrue(versions[1].closed)  # stale candidate was never published
        self.assertTrue(old.index.closed)
        self.assertEqual({item[0] for item in self.service.current.signature}, {'b.pdf', 'c.pdf', 'd.pdf'})

    def test_failed_build_preserves_old_version_and_explicit_retry(self):
        should_fail = [False]
        def builder(directory):
            if should_fail[0]:
                raise RuntimeError('test indexing failure')
            return FakeIndex(directory)
        self.setup_api(builder=builder)
        self.upload('a.pdf'); self.ready()
        old = self.service.current
        should_fail[0] = True
        with self.assertLogs('app.index_service', level='ERROR'):
            self.upload('b.pdf')
            with self.service.condition:
                self.assertTrue(self.service.condition.wait_for(lambda: self.service.failed is not None, timeout=3))
        self.assertIs(old, self.service.current)
        statuses = {d['name']: d['status'] for d in self.client.get('/documents').json()}
        self.assertEqual(statuses, {'a.pdf': 'indexed', 'b.pdf': 'failed'})
        self.assertEqual(self.client.post('/ask', json={'question': 'Q'}).status_code, 200)
        should_fail[0] = False
        self.assertEqual(self.client.post('/index/retry').status_code, 202)
        self.ready()
        self.assertIsNot(old, self.service.current)

    def test_delete_during_generation_discards_stale_answer(self):
        entered, release = Event(), Event()
        async def generate(question, chunks):
            entered.set(); await asyncio.to_thread(release.wait, 5)
            return 'Old document answer'
        self.setup_api(generator=generate)
        self.upload(); self.ready()
        with ThreadPoolExecutor(max_workers=1) as callers:
            future = callers.submit(self.client.post, '/ask', json={'question': 'Q'})
            try:
                self.assertTrue(entered.wait(3))
                self.client.delete('/documents', params={'filename': 'guide.pdf'})
            finally:
                release.set()
            response = future.result()
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Old document answer', response.text)

    def test_old_collection_lives_until_last_reader_finishes(self):
        entered, release = Event(), Event()
        class SlowIndex(FakeIndex):
            def retrieve(self, question, allowed, top_k=4):
                entered.set(); release.wait(5)
                return super().retrieve(question, allowed, top_k)
        self.setup_api(builder=SlowIndex)
        self.upload('a.pdf'); self.ready()
        old = self.service.current
        with ThreadPoolExecutor(max_workers=1) as callers:
            future = callers.submit(self.client.post, '/ask', json={'question': 'Q'})
            try:
                self.assertTrue(entered.wait(3))
                self.upload('b.pdf'); self.ready()
                self.assertFalse(old.index.closed)
            finally:
                release.set()
            self.assertEqual(future.result().status_code, 200)
        self.assertTrue(old.index.closed)


class AdmissionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_limit_rejects_before_reading_second_body(self):
        from app.concurrency import AdmissionMiddleware
        entered, release = asyncio.Event(), asyncio.Event()
        async def downstream(scope, receive, send):
            entered.set()
            await release.wait()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})
        middleware = AdmissionMiddleware(downstream, upload_limit=1)
        scope = {'type': 'http', 'path': '/documents', 'method': 'POST', 'headers': []}
        async def receive():
            return {'type': 'http.request', 'body': b'pdf', 'more_body': False}
        messages = []
        async def send(message):
            messages.append(message)
        first = asyncio.create_task(middleware(scope, receive, send))
        await asyncio.wait_for(entered.wait(), 1)
        async def unread():
            raise AssertionError('Rejected upload must not read or parse its body')
        try:
            await middleware(scope, unread, send)
            self.assertEqual(messages[0]['status'], 429)
        finally:
            release.set()
            await first

    async def test_streamed_upload_limit_without_content_length(self):
        from app.concurrency import AdmissionMiddleware
        async def downstream(*args):
            raise AssertionError('Oversize body reached parser')
        middleware = AdmissionMiddleware(downstream)
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b'x' * (6 * 1024 * 1024), 'more_body': True}
        async def send(message):
            messages.append(message)
        await middleware({'type': 'http', 'path': '/documents', 'method': 'POST', 'headers': []}, receive, send)
        self.assertEqual(messages[0]['status'], 413)
