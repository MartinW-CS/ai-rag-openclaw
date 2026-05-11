"""
Claude agent that exposes the RAG pipeline as a callable 'search_documents' tool.
The agent decides when to search and synthesizes a final cited answer.
Run: python app/openclaw_skill.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).parent))
from ingest import load_and_chunk_pdfs
from retriever import build_vector_store, retrieve

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
DATA_DIR = Path(__file__).parent / "data"
MAX_AGENT_TURNS = 5

AGENT_SYSTEM_PROMPT = """You are a retrieval-augmented research agent.
You have access to one tool: search_documents(query) — it returns the most relevant
chunks from the user's PDF library, each labeled with [Source: <file>, Page <n>].

Workflow:
1. When the user asks a question, call search_documents with a focused query.
2. If results are insufficient or ambiguous, call search_documents again with a refined query.
3. When you have enough context, give a final answer.

Rules:
- Ground answers ONLY in retrieved chunks. No outside knowledge.
- If the documents do not contain the answer, say so explicitly.
- Always cite sources in the format: (Source: <file_name>, Page <page_number>).

Final output format:
Answer:
<final answer>

Sources:
- <source 1>
- <source 2>
"""

TOOLS = [
    {
        "name": "search_documents",
        "description": "Search the indexed PDF library and return the top-k most relevant chunks for a query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A focused search query — what specific information are you looking for?",
                }
            },
            "required": ["query"],
        },
    }
]

def run_search(collection, embedder, query: str) -> str:
    """Execute the search_documents tool and format results for the agent."""
    retrieved = retrieve(collection, embedder, query)
    if not retrieved:
        return "No matching chunks found."
    return "\n\n".join(
        f"[Chunk {i} | Source: {m['source']}, Page {m['page']}]\n{doc}"
        for i, (doc, m) in enumerate(retrieved, start=1)
    )

def run_agent(client, collection, embedder, user_question: str) -> str:
    """Run the tool-use agent loop. Returns the final answer text."""
    messages = [{"role": "user", "content": user_question}]

    for _ in range(MAX_AGENT_TURNS):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=AGENT_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if b.type == "text")

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [agent searches]: {block.input['query']}")
                    result = run_search(collection, embedder, block.input["query"])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        return f"[agent stopped unexpectedly: {response.stop_reason}]"

    return "[agent hit max turns without finishing]"

def main():
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set in .env")

    print("Loading and chunking PDFs...")
    chunks = load_and_chunk_pdfs(DATA_DIR)
    print(f"  -> {len(chunks)} chunks")
    if not chunks:
        sys.exit("No chunks found. Put a PDF in app/data/ first.")

    print("Building vector store...")
    collection, embedder = build_vector_store(chunks)
    print(f"  -> {collection.count()} chunks indexed")

    client = Anthropic()
    print("\nAgent ready. Type a question (or 'quit' to exit).\n")
    while True:
        try:
            q = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in {"quit", "exit", "q"}:
            break

        print()
        print(run_agent(client, collection, embedder, q))
        print()

if __name__ == "__main__":
    main()