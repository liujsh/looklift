import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { AgentRunManifest, RuntimeSummary } from "../api/types";

export function AgentRunsPage({ client }: { client: LookliftClient }) {
  const [runs, setRuns] = useState<AgentRunManifest[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeSummary[]>([]);
  const [selected, setSelected] = useState<AgentRunManifest | null>(null);
  const [runtimeId, setRuntimeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [nextRuns, nextRuntimes] = await Promise.all([
      client.recoverableAgentRuns(),
      client.runtimes(),
    ]);
    setRuns(nextRuns);
    setRuntimes(nextRuntimes.filter((runtime) => runtime.id !== "fake"));
    setSelected((current) => nextRuns.find((run) => run.run_id === current?.run_id) ?? nextRuns[0] ?? null);
  };

  useEffect(() => { void load().catch((reason) => setError(String(reason))); }, []);
  useEffect(() => { setRuntimeId(selected?.runtime_id ?? ""); }, [selected?.run_id]);

  const resume = async () => {
    if (!selected || busy) return;
    setBusy(true);
    setError(null);
    try {
      await client.resumeAgentRun(selected.run_id, `attempt-${Date.now()}`, runtimeId || undefined);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  return <main className="agent-runs-page" aria-label="运行恢复">
    <header><p className="pane-kicker">AGENT RUNS</p><h1>运行恢复</h1><p>恢复会新建 Attempt，不会自动调用模型或应用候选。</p></header>
    {error && <p role="alert" className="platform-error">{error}</p>}
    <div className="agent-runs-layout">
      <section aria-label="可恢复运行">
        {runs.length === 0 && <p>没有需要恢复的运行。</p>}
        {runs.map((run) => <button key={run.run_id} type="button" data-active={selected?.run_id === run.run_id} onClick={() => setSelected(run)}>
          <strong>{run.run_id}</strong><span>{run.status}</span><small>{run.runtime_id ?? "未指定 Runtime"}</small>
        </button>)}
      </section>
      {selected && <section aria-label="运行详情" className="agent-run-detail">
        <h2>运行详情</h2>
        <dl>
          <dt>状态</dt><dd>{selected.status}</dd>
          <dt>Attempt</dt><dd>{selected.attempt_id ?? "—"}</dd>
          <dt>Provider / 模型</dt><dd>{selected.provider ?? "—"} / {selected.model ?? "—"}</dd>
          <dt>最后候选</dt><dd>{selected.last_candidate_revision ?? "尚无候选"}</dd>
          <dt>基线</dt><dd>{selected.baseline_hash.slice(0, 12)}</dd>
        </dl>
        {selected.status === "stale" ? <p role="status">正式基线已变化，只能查看，不能直接恢复。</p> : <>
          <label>继续使用 Runtime<select value={runtimeId} onChange={(event) => setRuntimeId(event.target.value)}>
            <option value="">沿用原 Runtime</option>
            {runtimes.map((runtime) => <option key={runtime.id} value={runtime.id}>{runtime.id}</option>)}
          </select></label>
          <button type="button" disabled={busy} onClick={resume}>{busy ? "正在创建…" : "新建 Attempt"}</button>
        </>}
      </section>}
    </div>
  </main>;
}
