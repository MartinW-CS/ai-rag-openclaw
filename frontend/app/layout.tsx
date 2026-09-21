import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Knowledge AI · 文档问答', description: '基于文档的回答，清晰可查的来源。' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
