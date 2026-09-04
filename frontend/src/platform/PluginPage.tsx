import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { PluginSummary } from "../api/types";
import { Icon } from "./icons";

export function PluginPage({ client }: { client: LookliftClient }) {
  const [plugins, setPlugins] = useState<PluginSummary[]>([]);
  const [projectId, setProjectId] = useState("default-project");
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [status, setStatus] = useState("正在读取插件…");
  const load = async () => { setPlugins(await client.plugins()); setStatus(""); };
  useEffect(() => { void load().catch(() => setStatus("插件读取失败")); }, [client]);
  const toggle = (id: string, capability: string) => setSelected((current) => {
    const values = new Set(current[id] ?? []);
    if (values.has(capability)) values.delete(capability); else values.add(capability);
    return { ...current, [id]: [...values] };
  });
  const grant = async (plugin: PluginSummary) => {
    setStatus("正在保存授权…");
    try {
      await client.grantPlugin(plugin.id, { project_id: projectId, capabilities: selected[plugin.id] ?? [], scope: "run" });
      await load();
      setStatus("授权已更新");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "授权失败"); }
  };
  const revoke = async (plugin: PluginSummary) => {
    setStatus("正在撤销授权…");
    try {
      await client.revokePlugin(plugin.id, projectId);
      await load();
      setStatus("授权已撤销");
    } catch (reason) { setStatus(reason instanceof Error ? reason.message : "撤销失败"); }
  };

  return (
    <main className="plugin-page" aria-label="插件管理">
      <header>
        <div>
          <p className="pane-kicker">Plugins</p>
          <h1>插件管理</h1>
          <p>插件只能使用 Manifest 已声明、且你明确授予的最小能力集合。</p>
        </div>
        <label className="plugin-project">项目范围
          <input value={projectId} onChange={(event) => setProjectId(event.target.value)} />
        </label>
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
              <span className={`pill ${plugin.enabled ? "official" : "missing"}`}>{plugin.enabled ? "可用" : "已禁用"}</span>
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
                    checked={(selected[plugin.id] ?? plugin.granted_capabilities).includes(capability)}
                    onChange={() => toggle(plugin.id, capability)}
                  />{capability}
                </label>
              ))}
            </fieldset>

            <small>摘要 {plugin.content_hash.slice(0, 12)} · 当前授权：{plugin.granted_capabilities.join("、") || "无"}</small>

            <div>
              <button type="button" disabled={!plugin.enabled} onClick={() => void grant(plugin)}>
                <Icon name="shield-check" />保存最小授权
              </button>
              <button type="button" onClick={() => void revoke(plugin)}>
                <Icon name="shield-off" />撤销授权
              </button>
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
    </main>
  );
}
