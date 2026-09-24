export type RetrievedChunk = {
  rank: number;
  chunk_id: string;
  index_id: string;
  source: string;
  page: number;
  text: string;
  distance: number;
  similarity_score: number | null;
};

export type RetrievalDetails = {
  distance_metric: 'squared_l2';
  similarity_metric: 'cosine';
  chunks: RetrievedChunk[];
};

export function RetrievalInspector({ retrieval, onOpen }: { retrieval?: RetrievalDetails; onOpen: (filename: string, page: number) => void }) {
  if (!retrieval) {
    return <section className="retrieval-inspector"><h3>检索片段</h3><p>本次回答未包含检索详情，请更新后端后重新提问。</p></section>;
  }
  return (
    <section className="retrieval-inspector" aria-label="Retrieval Inspector">
      <div className="retrieval-heading">
        <h3>检索片段 <span>{retrieval.chunks.length}</span></h3>
        <span className="section-label">RETRIEVAL INSPECTOR</span>
      </div>
      <p>以下片段按检索顺序提供给模型，用于生成本次回答。展开可查看完整原文。</p>
      <p className="score-help">按平方 L2 距离升序排列（越小越接近）。余弦相似度范围 −1 到 1，越大越相似；它不是答案正确率。</p>
      {!retrieval.chunks.length && <p>本次回答没有返回检索片段。</p>}
      <div className="retrieval-chunks">
        {retrieval.chunks.map(chunk => (
          <details className="retrieval-chunk" key={`${chunk.index_id}:${chunk.chunk_id}`}>
            <summary>
              <span className="chunk-rank">#{chunk.rank}</span>
              <span className="chunk-origin"><button type="button" className="chunk-source-link" onClick={event => { event.stopPropagation(); onOpen(chunk.source, chunk.page); }} aria-label={`查看片段 ${chunk.rank} 的原文：${chunk.source} 第 ${chunk.page} 页`}><strong>{chunk.source}</strong><small>第 {chunk.page} 页 · 查看原文 ↗</small></button></span>
              <span className="chunk-scores"><span>余弦相似度 <b>{chunk.similarity_score === null ? '不可用' : chunk.similarity_score.toFixed(3)}</b></span><span>L2 距离² <b>{chunk.distance.toFixed(4)}</b></span></span>
              <span className="chunk-toggle" aria-hidden="true">⌄</span>
              <span className="chunk-preview">{chunk.text}</span>
            </summary>
            <div className="chunk-content"><div className="chunk-id">{chunk.chunk_id} · 完整片段</div><p>{chunk.text}</p></div>
          </details>
        ))}
      </div>
    </section>
  );
}
