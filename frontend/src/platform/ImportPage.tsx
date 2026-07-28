import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { ImportItem, ImportSource, ImportTask } from "../api/types";

export function ImportPage({ client }: { client: LookliftClient }) {
  const [sources, setSources] = useState<ImportSource[]>([]);
  const [source, setSource] = useState("");
  const [items, setItems] = useState<ImportItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [date, setDate] = useState("");
  const [unimported, setUnimported] = useState(true);
  const [task, setTask] = useState<ImportTask | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { client.importSources().then(({ sources: found }) => { setSources(found); if (found[0]) setSource(found[0].id); }).catch((e) => setError(String(e))); }, [client]);
  useEffect(() => { if (!source) return; client.importItems(source, date, unimported).then(({ items: found }) => { setItems(found); setSelected(new Set()); }).catch((e) => setError(String(e))); }, [client, source, date, unimported]);
  useEffect(() => { if (!taskId || !task || task.status !== "running") return; const timer = window.setInterval(() => client.importTask(taskId).then(setTask), 700); return () => window.clearInterval(timer); }, [client, taskId, task]);
  const start = async () => { try { const result = await client.startImport([...selected]); setTaskId(result.task_id); setTask(await client.importTask(result.task_id)); } catch (e) { setError(String(e)); } };
  return <main className="library-page" aria-label="从设备导入"><p className="pane-kicker">IMPORT</p><h1>从设备导入</h1>
    {error && <div role="alert">{error}</div>}
    <label>来源 <select value={source} onChange={(e) => setSource(e.target.value)}>{sources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>日期 <input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
    <label><input type="checkbox" checked={unimported} onChange={(e) => setUnimported(e.target.checked)} />仅未导入</label>
    <button onClick={() => setSelected(new Set(items.map((item) => item.path)))}>全选</button><button disabled={!selected.size} onClick={start}>导入选中（{selected.size}）</button>
    <ul>{items.map((item) => <li key={item.path}><label><input type="checkbox" checked={selected.has(item.path)} disabled={item.duplicate && unimported} onChange={(e) => setSelected((old) => { const next = new Set(old); e.target.checked ? next.add(item.path) : next.delete(item.path); return next; })} />{item.name} · {item.format} · {Math.round(item.size / 1024)} KB{item.duplicate ? " · 已导入" : ""}</label></li>)}</ul>
    {task && <p role="status">{task.message}（{task.completed}/{task.total}，跳过 {task.skipped}）{task.status === "running" && taskId && <button onClick={() => client.cancelImport(taskId)}>取消</button>}</p>}
  </main>;
}
