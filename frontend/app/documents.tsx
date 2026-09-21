'use client';
import { useRef, useState } from 'react';
export type Document = { name: string; size: number; status: 'pending' | 'indexed' };
type Props = { documents: Document[]; loading: boolean; error: string; busy: boolean; working: boolean; setWorking: (value: boolean) => void; refresh: () => Promise<void>; changed: () => void };
export function DocumentSidebar({ documents, loading, error, busy, working, setWorking, refresh, changed }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState('');
  const [failure, setFailure] = useState('');
  const [removing, setRemoving] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const disabled = busy || working;
  async function mutate(url: string, options: RequestInit, success: string) {
    setWorking(true); setFailure(''); setMessage('');
    try {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '文档操作失败，请重试。');
      changed(); setRemoving(null); setMessage(success); await refresh();
    } catch (reason) { setFailure(reason instanceof Error ? reason.message : '操作失败，请重试。'); }
    finally { setWorking(false); }
  }
  async function upload(file?: File) {
    if (!file || disabled) return;
    setFailure(''); setMessage('');
    if (!file.name.toLowerCase().endsWith('.pdf')) { setFailure('请选择 PDF 文件。'); return; }
    if (file.size > 10 * 1024 * 1024) { setFailure('PDF 不能超过 10 MB。'); return; }
    const data = new FormData(); data.append('file', file);
    await mutate('/api/documents', { method: 'POST', body: data }, '上传成功，下次提问时自动更新索引。');
  }
  return <><div className="section-label">文档工作区</div><h2>你的知识，有据可循。</h2><p>上传 PDF，开始探索文档中的答案。</p>
    <input ref={input} type="file" accept=".pdf,application/pdf" hidden onChange={event => { void upload(event.target.files?.[0]); event.target.value = ''; }}/>
    <button className={`upload-zone ${dragging ? 'dragging' : ''}`} disabled={disabled} onClick={() => input.current?.click()} onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length !== 1) { setFailure('每次请上传一个 PDF。'); return; } void upload(event.dataTransfer.files[0]); }}><span aria-hidden="true">＋</span><strong>{working ? '正在处理…' : '上传 PDF'}</strong><small>点击选择或拖入文件 · 最大 10 MB</small></button>
    <div aria-live="polite">{message && <p>{message}</p>}{failure && <p role="alert" className="document-error">{failure}</p>}</div>
    <div className="section-label source-label">知识库文档 <span>{documents.length}</span></div><button className="refresh-documents" disabled={disabled || loading} onClick={() => void refresh()}>{loading ? '正在读取…' : '刷新列表 ↻'}</button>
    {error && <p role="alert" className="document-error">{error}</p>}{!loading && !error && !documents.length && <p>还没有文档。上传第一份 PDF 后即可提问。</p>}
    {documents.map(document => <div className="document-row" key={document.name}><div className="document-title">▤ <strong>{document.name}</strong></div><div className="document-meta"><span>{Math.max(1, Math.round(document.size / 1024))} KB · {document.status === 'indexed' ? '已索引' : '待索引'}</span><button disabled={disabled} aria-label={`移除 ${document.name}`} onClick={() => setRemoving(document.name)}>移除</button></div>{removing === document.name && <div className="remove-confirm"><p>从知识库移除此文档？</p><button disabled={disabled} onClick={() => void mutate(`/api/documents?filename=${encodeURIComponent(document.name)}`, { method: 'DELETE' }, '文档已移除，下次提问时自动更新索引。')}>确认移除</button><button disabled={disabled} onClick={() => setRemoving(null)}>取消</button></div>}</div>)}
    <p className="index-note">待索引文档会在下次提问时自动处理。暂不支持纯扫描或加密 PDF。</p><div className="sidebar-foot">基于文档回答 · 保留来源</div></>;
}
