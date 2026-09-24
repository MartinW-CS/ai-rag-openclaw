'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Markdown from 'react-markdown';
import dynamic from 'next/dynamic';
const PdfPreview = dynamic(() => import('./pdf-preview'), { ssr: false });
import { RetrievalInspector } from './retrieval-inspector';
import { DocumentSidebar, type Document } from './documents';
import { appendHistory, parseHistory, HISTORY_KEY, TOP_K_VALUES, type TopK, type Answer, type HistoryEntry } from '../lib/session-history';

type Source = { source: string; page: number };
const examples = ['这份文档的核心观点是什么？', '总结文档中的关键步骤', '有哪些需要注意的限制？'];

function CitationCard({ source, onOpen }: { source: Source; onOpen: (filename: string, page: number) => void }) {
  return <button type="button" className="citation citation-button" onClick={() => onOpen(source.source, source.page)} aria-label={`查看 ${source.source} 第 ${source.page} 页`}><span aria-hidden="true">▤</span><span><strong>{source.source}</strong><small>第 {source.page} 页 · 查看原文 ↗</small></span></button>;
}
export default function Home() {
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [previewOpen, setPreviewOpen] = useState(false);
  const previewTrigger = useRef<HTMLElement | null>(null);
  function openSource(filename: string, page: number) {
    previewTrigger.current = document.activeElement as HTMLElement;
    setSelectedDocument(filename); setSelectedPage(page); setPreviewOpen(true);
  }
  function closePreview() {
    setPreviewOpen(false);
    requestAnimationFrame(() => previewTrigger.current?.focus());
  }
  const [topK, setTopK] = useState<TopK>(4);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [historyNotice, setHistoryNotice] = useState('');
  const [activeHistory, setActiveHistory] = useState<string | null>(null);
  useEffect(() => {
    try { setHistory(parseHistory(sessionStorage.getItem(HISTORY_KEY))); }
    catch { setHistoryNotice('浏览器存储不可用，历史仅保留到刷新前。'); }
    setHistoryReady(true);
  }, []);
  useEffect(() => {
    if (!historyReady) return;
    try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history)); }
    catch {
      try { sessionStorage.removeItem(HISTORY_KEY); } catch {}
      setHistoryNotice('历史无法写入浏览器存储，当前记录仅保留到刷新前。');
    }
  }, [history, historyReady]);
  function showHistory(entry: HistoryEntry) {
    if (busy || documentBusy) return;
    setPreviewOpen(false); setError(''); setQuestion(entry.question); setAsked(entry.question);
    setResult(entry.result); setTopK(entry.topK); setActiveHistory(entry.id);
  }
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
  const refreshing = useRef(false);
  async function refreshDocuments() {
    if (refreshing.current) return;
    refreshing.current = true;
    setDocumentsLoading(true); setDocumentsError('');
    try {
      const response = await fetch('/api/documents'); const data = await response.json();
      if (!response.ok || !Array.isArray(data)) throw new Error(typeof data.detail === 'string' ? data.detail : '无法读取文档列表。');
      setDocuments(data);
    } catch (reason) { setDocumentsError(reason instanceof Error ? reason.message : '无法读取文档列表。'); }
    finally { refreshing.current = false; setDocumentsLoading(false); }
  }
  const sidebarProps = { onOpen: openSource, selectedDocument: previewOpen ? selectedDocument : null, documents, loading: documentsLoading, error: documentsError, busy, working: documentBusy, setWorking: setDocumentBusy, refresh: refreshDocuments, changed: () => { setPreviewOpen(false); setResult(null); setAsked(''); setError(''); } };
  async function checkHealth() {
    setStatus('checking');
    try { const response = await fetch('/api/health'); const data = await response.json(); setStatus(response.ok && data.status === 'ok' ? 'online' : 'offline'); }
    catch { setStatus('offline'); }
  }
  useEffect(() => { void checkHealth(); void refreshDocuments(); }, []);
  useEffect(() => {
    if (!documents.some(document => document.status === 'queued' || document.status === 'indexing')) return;
    const timer = setTimeout(() => { void refreshDocuments(); }, 2500);
    return () => clearTimeout(timer);
  }, [documents]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (!value || busy || documentBusy) return;
    setBusy(true); setError(''); setResult(null); setAsked(value); setPreviewOpen(false); setActiveHistory(null);
    const requestedTopK = topK;
    try {
      const response = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: value, top_k: requestedTopK }) });
      const data = await response.json();
      if (!response.ok) throw new Error((typeof data.detail === 'string' ? data.detail : '问题提交失败，请检查输入后重试。') + (response.headers.get('retry-after') ? ` 建议 ${response.headers.get('retry-after')} 秒后重试。` : ''));
      if (typeof data.answer !== 'string' || !Array.isArray(data.sources)) throw new Error('服务返回格式异常，请重试。');
      setResult(data);
      const entry: HistoryEntry = { id: crypto.randomUUID(), question: value, result: data, topK: requestedTopK };
      setHistory(previous => appendHistory(previous, entry));
    } catch (reason) { setError(reason instanceof Error ? reason.message : '请求失败，请重试。'); }
    finally { setBusy(false); void refreshDocuments(); }
  }
  return <div className="app-shell"><header><a className="brand" href="/"><span className="brand-mark">K</span>Knowledge AI<span className="brand-sub">文档问答</span></a><button className={`status ${status}`} onClick={checkHealth} aria-label="刷新后端连接状态"><i/>{status === 'checking' ? '检查连接中' : status === 'online' ? '服务已连接' : '服务未连接'}<span aria-hidden="true">↻</span></button></header><div className={`workspace ${previewOpen ? 'with-preview' : ''}`}><aside className="desktop-sidebar"><DocumentSidebar {...sidebarProps}/></aside><main><button className="mobile-toggle" onClick={() => setDrawer(!drawer)} aria-expanded={drawer} aria-controls="mobile-documents">{drawer ? '收起文档面板 −' : '文档工作区 +'}</button>{drawer && <aside id="mobile-documents" className="mobile-sidebar"><DocumentSidebar {...sidebarProps}/></aside>}<div className="content"><div className="eyebrow">工作区 <span>/</span> 文档问答</div><section className="intro"><div className="section-label">从问题到理解</div><h1>向你的文档提问。</h1><p>找到关键内容，让每个回答都有来源。</p></section><form onSubmit={submit} className="composer"><label htmlFor="question">你想了解什么？</label><textarea id="question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="例如：这份文档如何解释 RAG 的工作流程？" rows={3} disabled={busy}/><div className="composer-bottom"><label className="top-k-control">Top-K <select aria-label="Top-K 检索片段数" value={topK} disabled={busy || documentBusy} onChange={event => setTopK(Number(event.target.value) as TopK)}>{TOP_K_VALUES.map(value => <option key={value} value={value}>{value}</option>)}</select></label><button type="submit" disabled={busy || documentBusy || !question.trim()}>{busy ? '正在生成…' : '发送问题'} <span aria-hidden="true">↑</span></button></div></form><section className="session-history" aria-label="本次会话历史"><div className="history-heading"><h2>本次会话 · 最近 {history.length} 条</h2><button disabled={busy || documentBusy || !history.length} onClick={() => setHistory([])}>清空历史</button></div><p>每次提问独立；历史不发送给模型。当前标签页刷新后保留，最多 10 条。</p>{historyNotice && <p role="status">{historyNotice}</p>}<ol>{history.map(entry => <li key={entry.id}><button disabled={busy || documentBusy} aria-pressed={activeHistory === entry.id} onClick={() => showHistory(entry)}>{entry.question}<small>Top-K {entry.topK}</small></button></li>)}</ol></section>{!asked && <div className="examples">{examples.map(example => <button key={example} onClick={() => { setQuestion(example); document.getElementById('question')?.focus(); }}>{example}<span aria-hidden="true">↗</span></button>)}</div>}<div aria-live="polite" aria-busy={busy}>{busy && <div className="loading"><span className="spinner"/><div>正在查阅文档并生成回答…<small>正在检索已就绪的文档，请稍候。</small></div></div>}{error && <div role="alert" className="error"><strong>暂时无法回答</strong><p>{error}</p><span>问题已保留，可以再次点击发送。</span></div>}{result && <article className="answer"><div className="section-label">你的问题</div><h2>{asked}</h2>{activeHistory && <p className="history-warning">正在查看历史结果，不会重新检索。来源预览打开当前文件；文件可能已被修改或移除。</p>}<div className="answer-heading"><span className="brand-mark">K</span><h3>文档回答</h3></div><div className="prose"><Markdown>{result.answer}</Markdown></div><section className="sources"><h3>参考来源 <span>{result.sources.length}</span></h3><p>以下为检索命中的文档页；回答中的引用以正文为准。</p><div className="citation-grid">{result.sources.map(source => <CitationCard key={`${source.source}:${source.page}`} source={source} onOpen={openSource}/>)}</div>{!result.sources.length && <p>本次回答没有返回来源。</p>}</section><RetrievalInspector retrieval={result.retrieval} onOpen={openSource}/></article>}</div><footer>回答可能存在遗漏，请结合原文核实。</footer></div></main>{previewOpen && selectedDocument && <PdfPreview key={selectedDocument} filename={selectedDocument} page={selectedPage} onPage={setSelectedPage} onClose={closePreview}/>}</div></div>;
}
