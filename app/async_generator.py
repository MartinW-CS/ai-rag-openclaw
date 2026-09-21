"""A reusable, cancellable Claude client for the HTTP API only."""
from .generator import CLAUDE_MODEL, SYSTEM_PROMPT


class AsyncGenerator:
    def __init__(self):
        self.client = None

    async def __call__(self, question, retrieved):
        from anthropic import AsyncAnthropic
        if self.client is None:
            self.client = AsyncAnthropic(timeout=55.0, max_retries=0)
        context = '\n\n'.join(
            f"[Chunk {i} | Source: {meta['source']}, Page {meta['page']}]\n{text}"
            for i, (text, meta) in enumerate(retrieved, start=1)
        )
        response = await self.client.messages.create(
            model=CLAUDE_MODEL, max_tokens=1024, system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': f'Context:\n{context}\n\nQuestion: {question}'}],
        )
        return ''.join(block.text for block in response.content if block.type == 'text')

    async def close(self):
        if self.client is not None:
            await self.client.close()
