import { useEffect, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import type { LookliftClient } from "../api/client";
import type { LibraryItem, LibraryRoot } from "../api/types";

export function LibraryPage({ client, onOpen }: { client: LookliftClient; onOpen(path: string): Promise<void> | void }) {
  const [roots, setRoots] = useState<LibraryRoot[]>([]); const [items, setItems] = useState<LibraryItem[]>([]); const [path, setPath] = useState(""); const [keyword, setKeyword] = useState(""); const [tag, setTag] = useState(""); const [status, setStatus] = useState("");
  const refresh = async () => { const [rootResult, itemResult] = await Promise.all([client.libraryRoots(), client.libraryItems(keyword)]); setRoots(rootResult.roots); setItems(itemResult.items); };
  useEffect(() => { void refresh().catch(() => setStatus("图库读取失败")); }, []);
  const add = async (event: FormEvent) => { event.preventDefault(); try { const root = await client.addLibraryRoot(path); const result = await client.scanLibraryRoot(root.id); setPath(""); setStatus(`已索引 ${result.added} 个文件`); await refresh(); } catch (error) { setStatus(error instanceof Error ? error.message : "添加失败"); } };
  const search = async (event: FormEvent) => { event.preventDefault(); const result = await client.libraryItems(keyword, tag); setItems(result.items); };
  const saveTags = async (item: LibraryItem) => { const next = window.prompt("以逗号分隔标签", ""); if (next === null) return; await client.setLibraryTags(item.id, next.split(",")); setStatus("标签已保存"); };
  const reveal = async (path: string) => { if (!isTauri()) { setStatus("仅桌面应用可在资源管理器中定位文件"); return; } await revealItemInDir(path); };
  return <main className="coming-soon-page library-page" aria-label="我的图库"><p className="pane-kicker">LIBRARY</p><h1>我的图库</h1><p>只索引原文件，不复制或移动照片。</p><form onSubmit={add}><input value={path} onChange={(event) => setPath(event.target.value)} placeholder="输入本地文件夹路径" required /><button type="submit">加入图库</button></form><form onSubmit={search}><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索文件名或路径" /><input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="标签" /><button type="submit">搜索</button></form>{roots.length > 0 && <p>已加入 {roots.length} 个文件夹</p>}<div className="library-grid">{items.map((item) => <article key={item.id} data-available={item.available}><strong>{item.display_name}</strong><span>{item.available ? "可用" : "原文件已缺失"}</span><button type="button" disabled={!item.available} onClick={() => void onOpen(item.path)}>进入 Studio</button><button type="button" disabled={!item.available} onClick={() => void reveal(item.path)}>在资源管理器中显示</button><button type="button" onClick={() => void saveTags(item)}>编辑标签</button></article>)}</div>{status && <span role="status">{status}</span>}</main>;
}
