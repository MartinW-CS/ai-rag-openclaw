"""Claude API call with the grounded, cited system prompt."""
from anthropic import Anthropic

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """You are a retrieval-augmented assistant. Answer using ONLY the provided context.
- Ground answers strictly in the context. Do not introduce outside knowledge.
- If the context is insufficient, explicitly say so.
- Always cite sources in the format: (Source: <file_name>, Page <page_number>).

Output format:
Answer:
<final answer>

Sources:
- <source 1>
- <source 2>
"""

def ask_claude(query, retrieved):
    """Send query + retrieved context to Claude and return the answer text."""
    context = "\n\n".join(
        f"[Chunk {i} | Source: {m['source']}, Page {m['page']}]\n{doc}"
        for i, (doc, m) in enumerate(retrieved, start=1)
    )
    user_msg = f"Context:\n{context}\n\nQuestion: {query}"

    client = Anthropic()  # reads ANTHROPIC_API_KEY from environment
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text