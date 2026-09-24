'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.min.mjs';
const options = { cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/', isEvalSupported: false };
type Props = { filename: string; page: number; onPage: (page: number) => void; onClose: () => void };

export default function PdfPreview({ filename, page, onPage, onClose }: Props) {
  const [file, setFile] = useState<{ data: Uint8Array } | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [error, setError] = useState('');
  const [pageError, setPageError] = useState('');
  const [draft, setDraft] = useState(String(page));
  const [retry, setRetry] = useState(0);
  const [width, setWidth] = useState(400);
  const [mobile, setMobile] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const currentPage = numPages ? Math.min(Math.max(1, page), numPages) : page;
  const outOfRange = numPages > 0 && currentPage !== page;

  useEffect(() => {
    const media = window.matchMedia('(max-width: 800px)');
    const update = () => setMobile(media.matches);
    update(); media.addEventListener('change', update);
    close.current?.focus();
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!mobile) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = original; };
  }, [mobile]);
  useEffect(() => {
    if (!viewport.current) return;
    const observer = new ResizeObserver(entries => setWidth(Math.max(180, entries[0].contentRect.width - 24)));
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setDraft(String(currentPage)); setPageError('');
    viewport.current?.scrollTo({ top: 0 });
  }, [currentPage]);
  useEffect(() => {
    const controller = new AbortController();
    setFile(null); setNumPages(0); setError('');
    async function load() {
      try {
        const response = await fetch(`/api/documents/${encodeURIComponent(filename)}/file`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) {
          const body = await response.json();
          throw new Error(typeof body.detail === 'string' ? body.detail : '无法读取 PDF。');
        }
        const data = new Uint8Array(await response.arrayBuffer());
        if (!controller.signal.aborted) setFile({ data });
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'PDF 加载失败。');
      }
    }
    void load();
    return () => controller.abort();
  }, [filename, retry]);

  function jump(event: FormEvent) {
    event.preventDefault();
    const next = Number(draft);
    if (!Number.isInteger(next) || next < 1 || next > numPages) { setPageError(`请输入 1 到 ${numPages} 之间的页码。`); return; }
    setPageError(''); onPage(next);
  }
  return (
    <aside className="pdf-panel" ref={panel} role={mobile ? 'dialog' : 'region'} aria-modal={mobile || undefined} aria-label={`PDF 预览：${filename}`} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (mobile && event.key === 'Tab') {
        const controls = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]');
        if (!controls?.length) return;
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }}>
      <div className="pdf-panel-header"><div><span className="section-label">PDF 原文</span><h2>{filename}</h2></div><button ref={close} onClick={onClose} aria-label="关闭 PDF 预览">✕</button></div>
      <form className="pdf-toolbar" onSubmit={jump} aria-label="PDF 页码导航">
        <button type="button" disabled={!numPages || currentPage <= 1} onClick={() => onPage(currentPage - 1)} aria-label="上一页">←</button>
        <label>第 <input aria-label="PDF 页码" type="number" min={1} max={numPages || 1} value={draft} disabled={!numPages} onChange={event => setDraft(event.target.value)} /> / {numPages || '—'} 页</label>
        <button type="submit" disabled={!numPages}>跳转</button>
        <button type="button" disabled={!numPages || currentPage >= numPages} onClick={() => onPage(currentPage + 1)} aria-label="下一页">→</button>
      </form>
      <div className="pdf-status" aria-live="polite">{numPages > 0 && !error && <span>正在查看第 {currentPage} 页，共 {numPages} 页</span>}{outOfRange && <p role="alert">来源页码 {page} 超出当前 PDF 范围，已显示第 {currentPage} 页。文档可能已被替换。</p>}{pageError && <p role="alert">{pageError}</p>}</div>
      <div className="pdf-viewport" ref={viewport}>
        {error ? <div className="pdf-error" role="alert"><p>{error}</p><button onClick={() => setRetry(value => value + 1)}>重新加载 PDF</button></div> : file ? (
          <Document file={file} options={options} suspense={false} loading={<p className="pdf-message">正在解析 PDF…</p>} onLoadSuccess={({ numPages }) => setNumPages(numPages)} onLoadError={() => setError('PDF 无法解析，文件可能已损坏。')} onPassword={() => setError('此 PDF 已加密，暂不支持预览。')}>
            {numPages > 0 && <Page key={currentPage} pageNumber={currentPage} width={width} renderAnnotationLayer={false} renderTextLayer loading={<p className="pdf-message">正在渲染第 {currentPage} 页…</p>} onRenderError={() => setPageError('此页无法渲染，请尝试其他页。')} />}
          </Document>
        ) : <p className="pdf-message" role="status">正在加载 PDF…</p>}
      </div>
    </aside>
  );
}
