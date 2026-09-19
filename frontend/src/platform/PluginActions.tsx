import { useCallback, useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { PluginActionSummary, PluginConfirmationField } from "../api/types";

const STATE_LABELS: Record<PluginActionSummary["state"], string> = {
  pending_confirmation: "待你确认",
  confirmed: "已确认",
  executing: "执行中",
  succeeded: "已完成",
  failed: "执行失败",
  unknown: "结果未知",
  rejected: "已拒绝",
  cancelled: "已取消",
  expired: "已过期",
};

type Drafts = Record<string, Record<string, unknown>>;

function valueForInput(value: unknown): string {
  return value == null ? "" : String(value);
}

function fieldValue(field: PluginConfirmationField, value: string): unknown {
  return field.control === "number" && value !== "" ? Number(value) : value;
}

function shortHash(value: string): string {
  return `${value.slice(0, 8)}…${value.slice(-6)}`;
}

function formatExpiry(value: number | null): string {
  if (value == null) return "不过期";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(value * 1000));
}

export function PluginActions({ client, projectId }: { client: LookliftClient; projectId: string }) {
  const [actions, setActions] = useState<PluginActionSummary[]>([]);
  const [drafts, setDrafts] = useState<Drafts>({});
  const [status, setStatus] = useState("正在读取待确认操作…");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectId, setRejectId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("正在读取待确认操作…");
    try {
      const items = await client.pluginActions(projectId);
      setActions(items);
      setDrafts(Object.fromEntries(items.map((item) => [item.action_id, { ...item.arguments }])));
      setStatus("");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "待确认操作读取失败");
    }
  }, [client, projectId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setRejectId(null); }, [projectId]);

  const replaceAction = (next: PluginActionSummary) => {
    setActions((current) => current.map((item) => item.action_id === next.action_id ? next : item));
    setDrafts((current) => ({ ...current, [next.action_id]: { ...next.arguments } }));
  };

  const run = async (actionId: string, operation: () => Promise<PluginActionSummary>, success: string) => {
    setBusyId(actionId);
    setStatus("");
    try {
      replaceAction(await operation());
      setStatus(success);
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusyId(null);
    }
  };

  const updateField = (action: PluginActionSummary, field: PluginConfirmationField, value: string) => {
    setDrafts((current) => ({
      ...current,
      [action.action_id]: {
        ...(current[action.action_id] ?? action.arguments),
        [field.key]: fieldValue(field, value),
      },
    }));
  };

  return (
    <section className="plugin-actions" aria-labelledby="plugin-actions-title">
      <header>
        <div>
          <h2 id="plugin-actions-title">外部操作</h2>
          <p>发布前核对目标账号、素材和内容。确认按钮会立即调用对应平台。</p>
        </div>
        <button type="button" onClick={() => void load()}>刷新</button>
      </header>

      {status && <p role="status" className="plugin-inline-status">{status}</p>}

      <div className="action-list">
        {actions.map((action) => {
          const pending = action.state === "pending_confirmation";
          const cancellable = action.state === "confirmed" || action.state === "executing";
          const draft = drafts[action.action_id] ?? action.arguments;
          const dirty = JSON.stringify(draft) !== JSON.stringify(action.arguments);
          return (
            <article className="action-card" key={action.action_id} data-state={action.state}>
              <header>
                <div>
                  <span>外部写入</span>
                  <h3>{action.plugin_identity}</h3>
                </div>
                <span className="action-state">{STATE_LABELS[action.state]}</span>
              </header>

              <dl className="action-facts">
                <div><dt>目标账号</dt><dd>{action.account_id}</dd></div>
                <div><dt>素材</dt><dd>{action.asset_hashes.length} 张图片</dd></div>
                <div><dt>有效期</dt><dd>{formatExpiry(action.expires_at)}</dd></div>
                <div><dt>版本</dt><dd>revision {action.revision}</dd></div>
              </dl>

              {action.asset_hashes.length > 0 && (
                <ol className="action-assets" aria-label="素材顺序">
                  {action.asset_hashes.map((hash, index) => (
                    <li key={hash}><span>{index + 1}</span><code>{shortHash(hash)}</code></li>
                  ))}
                </ol>
              )}

              {pending && action.confirmation_fields.length > 0 && (
                <div className="action-fields">
                  {action.confirmation_fields.map((field) => {
                    const value = valueForInput(draft[field.key]);
                    if (field.control === "readonly") {
                      return <div className="action-readonly" key={field.key}><span>{field.label}</span><strong>{value || "未提供"}</strong></div>;
                    }
                    if (field.control === "textarea") {
                      return <label key={field.key}>{field.label}<textarea name={field.key} value={value} onChange={(event) => updateField(action, field, event.target.value)} /></label>;
                    }
                    if (field.control === "select") {
                      return (
                        <label key={field.key}>{field.label}
                          <select name={field.key} value={value} onChange={(event) => updateField(action, field, event.target.value)}>
                            {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
                          </select>
                        </label>
                      );
                    }
                    return <label key={field.key}>{field.label}<input name={field.key} type={field.control} value={value} onChange={(event) => updateField(action, field, event.target.value)} /></label>;
                  })}
                </div>
              )}

              {pending && action.confirmation_fields.length === 0 && (
                <p className="action-unmapped">该工具没有可编辑字段。请核对下方冻结参数后再确认。</p>
              )}

              {pending && (
                <details className="action-raw">
                  <summary>查看冻结参数</summary>
                  <pre>{JSON.stringify(draft, null, 2)}</pre>
                </details>
              )}

              {action.result && (
                <details className="action-raw" open>
                  <summary>执行结果</summary>
                  <pre>{JSON.stringify(action.result, null, 2)}</pre>
                </details>
              )}

              {(pending || cancellable) && (
                <div className="action-card-actions">
                  {pending && <>
                    <button type="button" disabled={busyId === action.action_id || !dirty} onClick={() => void run(
                      action.action_id,
                      () => client.revisePluginAction(action.action_id, projectId, action.revision, draft),
                      "修改已保存，请重新核对",
                    )}>保存修改</button>
                    <button className="primary" type="button" disabled={busyId === action.action_id || dirty} title={dirty ? "请先保存修改" : undefined} onClick={() => void run(
                      action.action_id,
                      () => client.confirmPluginAction(action.action_id, projectId, action.revision),
                      "操作已执行",
                    )}>确认并执行</button>
                    {rejectId === action.action_id ? (
                      <button className="danger" type="button" disabled={busyId === action.action_id} onClick={() => void run(
                        action.action_id,
                        () => client.rejectPluginAction(action.action_id, projectId),
                        "操作已拒绝",
                      )}>确认拒绝</button>
                    ) : <button type="button" onClick={() => setRejectId(action.action_id)}>拒绝</button>}
                  </>}
                  {cancellable && <button className="danger" type="button" disabled={busyId === action.action_id} onClick={() => void run(
                    action.action_id,
                    () => client.cancelPluginAction(action.action_id, projectId),
                    "操作已取消",
                  )}>取消操作</button>}
                </div>
              )}
            </article>
          );
        })}

        {actions.length === 0 && !status && (
          <div className="connector-empty">当前项目没有待处理或历史外部操作。</div>
        )}
      </div>
    </section>
  );
}
