import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { PluginSummary } from "../api/types";
import { Icon } from "./icons";
import { PluginConnections } from "./PluginConnections";
import { PluginActions } from "./PluginActions";

const pluginKey = (plugin: Pick<PluginSummary, "id" | "version">) => `${plugin.id}@${plugin.version}`;

export function PluginPage({ client }: { client: LookliftClient }) {
  const [plugins, setPlugins] = useState<PluginSummary[]>([]);
  const [projectId, setProjectId] = useState("default-project");
  const [projectDraft, setProjectDraft] = useState("default-project");
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [connectionTarget, setConnectionTarget] = useState<string | null>(null);
  const [stateTarget, setStateTarget] = useState<string | null>(null);
  const [status, setStatus] = useState("正在读取插件…");
  const load = async () => {
    const items = await client.plugins(projectId, true);
    setPlugins(items);
    setSelected(Object.fromEntries(items.map((plugin) => [pluginKey(plugin), plugin.granted_capabilities])));
    setStatus("");
  };
  useEffect(() => { void load().catch(() => setStatus("插件读取失败")); }, [client, projectId]);
  useEffect(() => { setConnectionTarget(null); }, [projectId]);
  const toggle = (id: string, capability: string) => setSelected((current) => {
    const values = new Set(current[id] ?? []);
    if (values.has(capability)) values.delete(capability); else values.add(capability);
    return { ...current, [id]: [...values] };
  });
  const grant = async (plugin: PluginSummary) => {
    setStatus("正在保存授权…");
    try {
      await client.grantPlugin(plugin.id, { project_id: projectId, version: plugin.version, capabilities: selected[pluginKey(plugin)] ?? [], scope: "run" });
      await load();
      setStatus("授权已更新");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "授权失败"); }
  };
  const revoke = async (plugin: PluginSummary) => {
    setStatus("正在撤销授权…");
    try {
      await client.revokePlugin(plugin.id, plugin.version, projectId);
      await load();
      setStatus("授权已撤销");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "撤销失败"); }
  };
  const setEnabled = async (plugin: PluginSummary, enabled: boolean) => {
    setStatus(enabled ? "正在重新启用插件…" : "正在停用插件…");
    try {
      await client.setPluginEnabled(plugin.id, plugin.version, enabled);
      await load();
      setStateTarget(null);
      if (!enabled && connectionTarget === pluginKey(plugin)) setConnectionTarget(null);
      setStatus(enabled ? "插件已重新启用，需要重新授权后才能调用" : "插件已停用，相关授权与在线连接已收敛");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "插件状态更新失败"); }
  };
  const cleanup = async (plugin: PluginSummary) => {
    setStatus("正在安全清理插件包…");
    try {
      await client.cleanupPlugin(plugin.id, plugin.version);
      await load();
      setStateTarget(null);
      if (connectionTarget === pluginKey(plugin)) setConnectionTarget(null);
      setStatus("插件包已清理，Manifest 与审计历史仍保留");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "插件包清理失败"); }
  };

  return (
    <main className="plugin-page" aria-label="插件管理">
      <header>
        <div>
          <p className="pane-kicker">Plugins</p>
          <h1>插件管理</h1>
          <p>插件只能使用 Manifest 已声明、且你明确授予的最小能力集合。</p>
        </div>
        <form className="plugin-project" onSubmit={(event) => {
          event.preventDefault();
          const next = projectDraft.trim();
          if (next) setProjectId(next);
        }}>
          <label>项目范围<input required pattern="[a-z0-9][a-z0-9_-]{0,63}" value={projectDraft} onChange={(event) => setProjectDraft(event.target.value)} /></label>
          <button type="submit">载入项目</button>
        </form>
      </header>

      {status && <p role="status" className="settings-status">{status}</p>}

      <div className="plugin-list">
        {plugins.map((plugin) => (
          <article key={`${plugin.id}:${plugin.version}`} className="plugin-card">
            <header>
              <div>
                <span className="plugin-mark" aria-hidden="true"><Icon name="plugin" /></span>
                <div>
                  <h2>{plugin.id}</h2>
                  <p>{plugin.source} · v{plugin.version} · {plugin.kind}</p>
                </div>
              </div>
              <span className={`pill ${plugin.enabled ? "official" : "missing"}`}>
                {plugin.enabled ? "可用" : plugin.installed ? "已禁用" : "包已清理"}
              </span>
            </header>

            <div className="plugin-capsules">
              <span>输入 {plugin.inputs.join("、") || "无"}</span>
              <span>模式 {plugin.mode}</span>
            </div>

            <fieldset disabled={!plugin.enabled}>
              <legend>请求能力</legend>
              {plugin.capabilities.map((capability) => (
                <label key={capability}>
                  <input
                    type="checkbox"
                    checked={(selected[pluginKey(plugin)] ?? plugin.granted_capabilities).includes(capability)}
                    onChange={() => toggle(pluginKey(plugin), capability)}
                  />{capability}
                </label>
              ))}
            </fieldset>

            <small>摘要 {plugin.content_hash.slice(0, 12)} · 当前授权：{plugin.granted_capabilities.join("、") || "无"}</small>

            <div className="plugin-card-actions">
              <button type="button" disabled={!plugin.enabled} onClick={() => void grant(plugin)}>
                <Icon name="shield-check" />保存最小授权
              </button>
              <button type="button" onClick={() => void revoke(plugin)}>
                <Icon name="shield-off" />撤销授权
              </button>
              {plugin.enabled && plugin.services.length > 0 && (
                <button type="button" onClick={() => setConnectionTarget(pluginKey(plugin))}>连接账号</button>
              )}
              {plugin.source !== "builtin" && plugin.enabled && (
                stateTarget === pluginKey(plugin) ? <>
                  <button type="button" className="danger" onClick={() => void setEnabled(plugin, false)}>确认停用</button>
                  <button type="button" onClick={() => setStateTarget(null)}>取消</button>
                </> : <button type="button" className="quiet-danger" onClick={() => setStateTarget(pluginKey(plugin))}>停用</button>
              )}
              {plugin.source !== "builtin" && !plugin.enabled && plugin.installed && (
                stateTarget === pluginKey(plugin) ? <>
                  <button type="button" className="danger" onClick={() => void cleanup(plugin)}>确认清理</button>
                  <button type="button" onClick={() => setStateTarget(null)}>取消</button>
                </> : <>
                  <button type="button" onClick={() => void setEnabled(plugin, true)}>重新启用</button>
                  <button type="button" className="quiet-danger" onClick={() => setStateTarget(pluginKey(plugin))}>清理包</button>
                </>
              )}
            </div>
          </article>
        ))}

        {plugins.length === 0 && !status && (
          <div className="plugin-empty">
            <span aria-hidden="true"><Icon name="package-plus" /></span>
            <strong>还没有第三方插件</strong>
            <span>放入 Manifest 后会出现在这里，授权始终由你逐项确认。</span>
          </div>
        )}
      </div>

      <PluginConnections
        client={client}
        projectId={projectId}
        plugins={plugins}
        targetId={connectionTarget}
        onTargetChange={setConnectionTarget}
      />
      <PluginActions client={client} projectId={projectId} />
    </main>
  );
}
