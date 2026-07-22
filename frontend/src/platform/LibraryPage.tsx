import { useEffect, useRef, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { LookliftClient } from "../api/client";
import type { LibraryItem, LibraryRoot, LibraryScanTask } from "../api/types";
import { LibraryCard } from "./LibraryCard";
import { waitForLibraryScan } from "./libraryWorkflow";

const PAGE_SIZE = 48;

type LibraryPageProps = {
  client: LookliftClient;
  onOpen(path: string): Promise<void> | void;
};

export function LibraryPage({ client, onOpen }: LibraryPageProps) {
  const [roots, setRoots] = useState<LibraryRoot[]>([]);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [path, setPath] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [filters, setFilters] = useState({ keyword: "", tag: "" });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [scan, setScan] = useState<(LibraryScanTask & { id: string }) | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const activeScanId = useRef<string | null>(null);
  const scanRunning = useRef(false);

  const loadItems = async (nextPage: number, nextFilters = filters) => {
    const result = await client.libraryItems(
      nextFilters.keyword,
      nextFilters.tag,
      nextPage,
      PAGE_SIZE,
    );
    setItems(result.items);
    setTotal(result.total);
    setPage(result.page);
  };

  const refresh = async (nextPage = page, nextFilters = filters) => {
    setError("");
    const [rootResult] = await Promise.all([
      client.libraryRoots(),
      loadItems(nextPage, nextFilters),
    ]);
    setRoots(rootResult.roots);
  };

  useEffect(() => {
    let active = true;
    void refresh(1, { keyword: "", tag: "" })
      .catch((reason) => active && setError(message(reason, "图库读取失败")))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      pollController.current?.abort();
      if (activeScanId.current) void client.cancelLibraryScan(activeScanId.current).catch(() => undefined);
    };
  }, []);

  const runScan = async (rootId: string) => {
    if (scanRunning.current) return;
    scanRunning.current = true;
    setError("");
    let started: { task_id: string };
    try {
      started = await client.scanLibraryRoot(rootId);
    } catch (reason) {
      scanRunning.current = false;
      setError(message(reason, "图库扫描启动失败"));
      return;
    }
    const controller = new AbortController();
    pollController.current = controller;
    activeScanId.current = started.task_id;
    setScan({ id: started.task_id, status: "running", message: "准备扫描", result: null, error: null, scanned: 0, current: null });
    try {
      const finished = await waitForLibraryScan(
        client,
        started.task_id,
        (task) => setScan({ id: started.task_id, ...task }),
        controller.signal,
      );
      if (finished.status === "done" && finished.result) {
        setStatus(`扫描完成：新增 ${finished.result.added}，更新 ${finished.result.updated}，缺失 ${finished.result.missing}`);
      } else if (finished.status === "cancelled") {
        setStatus("扫描已取消，已完成的索引已保留");
      } else if (finished.status === "error") {
        setError(finished.error ?? "图库扫描失败");
      }
      await refresh(1);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(message(reason, "图库扫描失败"));
      }
    } finally {
      if (pollController.current === controller) pollController.current = null;
      if (activeScanId.current === started.task_id) activeScanId.current = null;
      scanRunning.current = false;
      setScan(null);
    }
  };

  const add = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const root = await client.addLibraryRoot(path);
      setPath("");
      await refresh(1);
      await runScan(root.id);
    } catch (reason) {
      setError(message(reason, "添加图库失败"));
    }
  };

  const chooseRoot = async () => {
    if (!isTauri()) {
      setError("浏览器开发模式请直接输入本地文件夹路径");
      return;
    }
    const selected = await open({ directory: true, multiple: false, title: "选择图库文件夹" });
    if (selected) setPath(selected);
  };

  const removeRoot = async (id: string) => {
    try {
      await client.removeLibraryRoot(id);
      setStatus("已移除图库索引，原文件未改变");
      await refresh(1);
    } catch (reason) {
      setError(message(reason, "移除索引失败"));
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const nextFilters = { keyword: keywordInput.trim(), tag: tagInput.trim() };
    setFilters(nextFilters);
    try {
      await loadItems(1, nextFilters);
    } catch (reason) {
      setError(message(reason, "图库搜索失败"));
    }
  };

  const saveTags = async (item: LibraryItem) => {
    const next = window.prompt("以逗号分隔标签", item.tags.join(", "));
    if (next === null) return;
    try {
      await client.setLibraryTags(item.id, next.split(","));
      setStatus("标签已保存");
      await loadItems(page);
    } catch (reason) {
      setError(message(reason, "标签保存失败"));
    }
  };

  const reveal = async (item: LibraryItem) => {
    try {
      await client.revealLibraryItem(item.id);
    } catch (reason) {
      setError(message(reason, "无法在资源管理器中定位文件"));
    }
  };

  const openStudio = async (item: LibraryItem) => {
    try {
      await onOpen(item.path);
    } catch (reason) {
      setError(message(reason, "Studio 打开失败"));
    }
  };

  const cancelScan = async () => {
    if (!scan) return;
    try {
      await client.cancelLibraryScan(scan.id);
      setStatus("正在停止扫描…");
    } catch (reason) {
      setError(message(reason, "停止扫描失败"));
    }
  };

  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const changePage = async (nextPage: number) => {
    try {
      await loadItems(nextPage);
    } catch (reason) {
      setError(message(reason, "图库翻页失败"));
    }
  };
  return (
    <main className="library-page" aria-label="我的图库">
      <header className="library-heading">
        <div><p className="pane-kicker">LIBRARY</p><h1>我的图库</h1></div>
        <p>只建立本地索引，不复制、移动或删除原文件。</p>
      </header>

      <section className="library-toolbar" aria-label="图库管理">
        <form onSubmit={add} data-form="add-root">
          <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="输入本地文件夹路径" required />
          <button type="button" onClick={() => void chooseRoot()}>选择文件夹</button>
          <button type="submit" disabled={Boolean(scan)}>加入图库</button>
        </form>
        <form onSubmit={search} data-form="search">
          <input value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} placeholder="搜索文件名或路径" />
          <input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="标签" />
          <button type="submit">搜索</button>
        </form>
      </section>

      {roots.length > 0 && <section className="library-roots" aria-label="索引文件夹">
        {roots.map((root) => <div key={root.id}>
          <span title={root.path}>{root.path}</span>
          <button type="button" disabled={Boolean(scan)} onClick={() => void runScan(root.id)}>刷新</button>
          <button type="button" disabled={Boolean(scan)} onClick={() => void removeRoot(root.id)}>移除索引</button>
        </div>)}
      </section>}

      {scan && <section className="library-scan" aria-live="polite">
        <span>{scan.message ?? `正在扫描 ${scan.current ?? ""}`}</span>
        <button type="button" onClick={() => void cancelScan()}>停止扫描</button>
      </section>}
      {error && <div className="library-message error" role="alert">{error}</div>}
      {status && <div className="library-message" role="status">{status}</div>}

      {loading ? <p className="library-empty">正在读取图库…</p> : items.length === 0 ? <p className="library-empty">没有符合条件的照片</p> : <div className="library-grid">
        {items.map((item) => <LibraryCard key={item.id} item={item} onOpen={openStudio} onReveal={reveal} onTags={saveTags} />)}
      </div>}

      <footer className="library-pagination">
        <span>共 {total} 张 · 第 {page}/{lastPage} 页</span>
        <button type="button" disabled={page <= 1} onClick={() => void changePage(page - 1)}>上一页</button>
        <button type="button" data-action="next-page" disabled={page >= lastPage} onClick={() => void changePage(page + 1)}>下一页</button>
      </footer>
    </main>
  );
}

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
