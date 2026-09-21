'use client';
import { useEffect, useState, type FormEvent } from 'react';
import Markdown from 'react-markdown';
import { DocumentSidebar, type Document } from './documents';

type Source = { source: string; page: number };
type Answer = { answer: string; sources: Source[] };
const examples = ['这份文档的核心观点是什么？', '总结文档中的关键步骤', '有哪些需要注意的限制？'];

function CitationCard({ source }: { source: Source }) {
  return <div className="citation"><span aria-hidden="true">▤</span><div><strong>{source.source}</strong><small>第 {source.page} 页</small></div></div>;
}
export default function Home() {
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState('');
  const [result, setResult] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [drawer, setDrawer] = useState(false);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState('');
  async function refreshDocuments() {
    setDocumentsLoading(true); setDocumentsError('');
    try {
      const response = await fetch('/api/documents'); const data = await response.json();
      if (!response.ok || !Array.isArray(data)) throw new Error(typeof data.detail === 'string' ? data.detail : '无法读取文档列表。');
      setDocuments(data);
    } catch (reason) { setDocumentsError(reason instanceof Error ? reason.message : '无法读取文档列表。'); }
    finally { setDocumentsLoading(false); }
  }
  const sidebarProps = { documents, loading: documentsLoading, error: documentsError, busy, working: documentBusy, setWorking: setDocumentBusy, refresh: refreshDocuments, changed: () => { setResult(null); setAsked(''); setError(''); } };
  async function checkHealth() {
    setStatus('checking');
    try { const response = await fetch('/api/health'); const data = await response.json(); setStatus(response.ok && data.status === 'ok' ? 'online' : 'offline'); }
    catch { setStatus('offline'); }
  }
  useEffect(() => { void checkHealth(); void refreshDocuments(); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (!value || busy || documentBusy) return;
    setBusy(true); setError(''); setResult(null); setAsked(value);
    try {
      const response = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '问题提交失败，请检查输入后重试。');
      if (typeof data.answer !== 'string' || !Array.isArray(data.sources)) throw new Error('服务返回格式异常，请重试。');
      setResult(data);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '请求失败，请重试。'); }
    finally { setBusy(false); void refreshDocuments(); }
  }
  return <div className="app-shell"><header><a className="brand" href="/"><span className="brand-mark">K</span>Knowledge AI<span className="brand-sub">文档问答</span></a><button className={`status ${status}`} onClick={checkHealth} aria-label="刷新后端连接状态"><i/>{status === 'checking' ? '检查连接中' : status === 'online' ? '服务已连接' : '服务未连接'}<span aria-hidden="true">↻</span></button></header><div className="workspace"><aside className="desktop-sidebar"><DocumentSidebar {...sidebarProps}/></aside><main><button className="mobile-toggle" onClick={() => setDrawer(!drawer)} aria-expanded={drawer} aria-controls="mobile-documents">{drawer ? '收起文档面板 −' : '文档工作区 +'}</button>{drawer && <aside id="mobile-documents" className="mobile-sidebar"><DocumentSidebar {...sidebarProps}/></aside>}<div className="content"><div className="eyebrow">工作区 <span>/</span> 文档问答</div><section className="intro"><div className="section-label">从问题到理解</div><h1>向你的文档提问。</h1><p>找到关键内容，让每个回答都有来源。</p></section><form onSubmit={submit} className="composer"><label htmlFor="question">你想了解什么？</label><textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="例如：这份文档如何解释 RAG 的工作流程？" rows={3} disabled={busy}/><div className="composer-bottom"><span>基于当前 PDF 知识库</span><button type="submit" disabled={busy || documentBusy || !question.trim()}>{busy ? '正在生成…' : '发送问题'} <span aria-hidden="true">↑</span></button></div></form>{!asked && <div className="examples">{examples.map(example => <button key={example} onClick={() => { setQuestion(example); document.getElementById('question')?.focus(); }}>{example}<span aria-hidden="true">↗</span></button>)}</div>}<div aria-live="polite" aria-busy={busy}>{busy && <div className="loading"><span className="spinner"/><div>正在查阅文档并生成回答…<small>首次提问需要初始化索引，可能耗时较长。</small></div></div>}{error && <div role="alert" className="error"><strong>暂时无法回答</strong><p>{error}</p><span>问题已保留，可以再次点击发送。</span></div>}{result && <article className="answer"><div className="section-label">你的问题</div><h2>{asked}</h2><div className="answer-heading"><span className="brand-mark">K</span><h3>文档回答</h3></div><div className="prose"><Markdown>{result.answer}</Markdown></div><section className="sources"><h3>参考来源 <span>{result.sources.length}</span></h3><p>以下为检索命中的文档页；回答中的引用以正文为准。</p><div className="citation-grid">{result.sources.map(source => <CitationCard key={`${source.source}:${source.page}`} source={source}/>)}</div>{!result.sources.length && <p>本次回答没有返回来源。</p>}</section></article>}</div><footer>回答可能存在遗漏，请结合原文核实。</footer></div></main></div></div>;
}
