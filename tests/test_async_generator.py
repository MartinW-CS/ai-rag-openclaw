from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from app.async_generator import AsyncGenerator


class GeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_is_reused_bounded_and_closed(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text', text='Answer')]))), close=AsyncMock())
        with patch('anthropic.AsyncAnthropic', return_value=client) as factory:
            generator = AsyncGenerator()
            for _ in range(2):
                self.assertEqual(await generator('Q', [('Text', {'source': 'a.pdf', 'page': 1})]), 'Answer')
            factory.assert_called_once_with(timeout=55.0, max_retries=0)
            self.assertIn('Source: a.pdf', client.messages.create.call_args.kwargs['messages'][0]['content'])
            await generator.close()
            client.close.assert_awaited_once()
