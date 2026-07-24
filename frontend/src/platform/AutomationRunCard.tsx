import type { AutomationRun } from "../api/types";

export function AutomationRunCard({ run, active = false, busy = false, onCancel, onRetry, onSelect }: {
  run: AutomationRun;
  active?: boolean;
  busy?: boolean;
  onCancel?(): void;
  onRetry?(): void;
  onSelect?(): void;
}) {
  const interrupted = run.items.filter((item) => item.status === "interrupted").length;
  const retryable = run.failed + run.cancelled + interrupted;
  const problems = run.items.filter((item) => ["failed", "cancelled", "interrupted"].includes(item.status));
  return <article className="automation-run" data-status={run.status}>
    <div>
      <strong>{run.workflow.name}</strong>
      <span>{run.completed}/{run.total} 完成 · {run.failed} 失败 · {run.cancelled} 取消</span>
    </div>
    {active ? <div>
      {run.status === "running" && <button type="button" onClick={onCancel}>停止任务</button>}
      {run.status !== "running" && retryable > 0 && <button type="button" disabled={busy} onClick={onRetry}>只重试失败项</button>}
    </div> : <button type="button" onClick={onSelect}>查看详情</button>}
    {active && <div className="automation-run-items">
      {problems.length === 0
        ? <span>全部成片已生成，原照片未改变。</span>
        : problems.slice(0, 20).map((item) => <div key={`${item.source}:${item.output}`}>
          <strong>{fileName(item.source)}</strong>
          <span>{item.error ?? statusLabel(item.status)}</span>
        </div>)}
      {problems.length > 20 && <small>另有 {problems.length - 20} 个问题项目</small>}
    </div>}
  </article>;
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function statusLabel(status: string): string {
  return { failed: "执行失败", cancelled: "已取消", interrupted: "上次运行中断" }[status] ?? status;
}
