import type { RetrievalDetails } from '../app/retrieval-inspector';

export type TopK = 2 | 4 | 6 | 8;
export type Answer = { answer: string; sources: { source: string; page: number }[]; retrieval?: RetrievalDetails };
export type HistoryEntry = { id: string; question: string; result: Answer; topK: TopK };
export const HISTORY_KEY = 'rag-session-history-v1';
export const TOP_K_VALUES: TopK[] = [2, 4, 6, 8];
export function appendHistory(entries: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  return [entry, ...entries].slice(0, 10);
}
// Storage is optional and untrusted: a corrupt/older entry must not break rendering.
export function parseHistory(raw: string | null): HistoryEntry[] {
  try {
    const items = JSON.parse(raw || '[]');
    if (!Array.isArray(items)) return [];
    return items.filter((item): item is HistoryEntry => {
      if (!item || typeof item.id !== 'string' || typeof item.question !== 'string' || !TOP_K_VALUES.includes(item.topK)) return false;
      const result = item.result;
      if (!result || typeof result.answer !== 'string' || !Array.isArray(result.sources)) return false;
      const sourceValid = (source: { source?: unknown; page?: unknown } | null) => source && typeof source.source === 'string' && Number.isInteger(source.page) && Number(source.page) > 0;
      if (!result.sources.every(sourceValid)) return false;
      const retrieval = result.retrieval;
      if (retrieval === undefined) return true;
      return retrieval && retrieval.distance_metric === 'squared_l2' && retrieval.similarity_metric === 'cosine'
        && (retrieval.top_k === undefined || TOP_K_VALUES.includes(retrieval.top_k))
        && Array.isArray(retrieval.chunks) && retrieval.chunks.every((chunk: Record<string, unknown>) => sourceValid(chunk)
          && Number.isInteger(chunk.rank) && Number(chunk.rank) > 0 && typeof chunk.chunk_id === 'string'
          && typeof chunk.index_id === 'string' && typeof chunk.text === 'string' && Number.isFinite(chunk.distance)
          && (chunk.similarity_score === null || Number.isFinite(chunk.similarity_score)));
    }).slice(0, 10);
  } catch { return []; }
}
