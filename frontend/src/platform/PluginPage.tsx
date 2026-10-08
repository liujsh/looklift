import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { PluginCatalogItem, PluginCatalogSnapshot, PluginSummary } from "../api/types";
import { Icon } from "./icons";
import { PluginConnections } from "./PluginConnections";
import { PluginActions } from "./PluginActions";

const pluginKey = (plugin: Pick<PluginSummary, "id" | "version">) => `${plugin.id}@${plugin.version}`;

export function PluginPage({ client }: { client: LookliftClient }) {
  const [plugins, setPlugins] = useState<PluginSummary[]>([]);
  const [catalog, setCatalog] = useState<PluginCatalogSnapshot | null>(null);
  const [catalogStatus, setCatalogStatus] = useState("正在读取官方目录…");
  const [installTarget, setInstallTarget] = useState<PluginCatalogItem | null>(null);
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
  const loadCatalog = async () => {
    const snapshot = await client.pluginCatalog();
    setCatalog(snapshot);
    setCatalogStatus(snapshot.stale ? "当前为过期缓存，仅供查看，请刷新后再安装" : "");
  };
  useEffect(() => {
    void loadCatalog().catch((reason) => {
      setCatalog(null);
      setCatalogStatus(reason instanceof Error ? reason.message : "官方目录不可用");
    });
  }, [client]);
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
  const refreshCatalog = async () => {
    setCatalogStatus("正在刷新验签目录…");
    try {
      const snapshot = await client.refreshPluginCatalog();
      setCatalog(snapshot);
      setCatalogStatus("目录已刷新并通过签名校验");
    } catch (reason) { setCatalogStatus(reason instanceof Error ? reason.message : "目录刷新失败"); }
  };
  const installCatalogItem = async (item: PluginCatalogItem) => {
    setCatalogStatus(`正在安装 ${item.name} v${item.version}…`);
    try {
      await client.installCatalogPlugin(item.name, item.version);
      await Promise.all([load(), loadCatalog()]);
      setInstallTarget(null);
      setCatalogStatus(`${item.name} v${item.version} 已安装，启用前请核对并授予最小能力`);
    } catch (reason) { setCatalogStatus(reason instanceof Error ? reason.message : "目录插件安装失败"); }
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

      <section className="plugin-catalog" aria-label="官方精选目录">
        <header>
          <div>
            <p className="pane-kicker">Verified catalog</p>
            <h2>官方精选目录</h2>
            <p>这里只展示通过应用内公钥校验的固定版本；目录发现不会自动获得执行权限。</p>
          </div>
          <button type="button" onClick={() => void refreshCatalog()}>刷新目录</button>
        </header>
        {catalogStatus && <p role="status" className="settings-status">{catalogStatus}</p>}
        {catalog && <small>目录 revision {catalog.revision}{catalog.stale ? " · 缓存已过期" : " · 签名有效"}</small>}
        <div className="plugin-catalog-list">
          {catalog?.plugins.map((item) => (
            <article key={`${item.name}@${item.version}`} className="plugin-catalog-item">
              <div>
                <strong>{item.name} <span>v{item.version}</span></strong>
                <small>{item.license} · {item.platforms.join("、")}</small>
                <p>{item.capabilities.join("、") || "不请求额外能力"}</p>
              </div>
              {item.revoked ? <span className="pill missing">已撤销</span>
                : item.installed ? <span className="pill official">{item.package_present ? "已安装" : "历史已清理"}</span>
                : !item.compatible ? <span className="pill missing">平台不兼容</span>
                : installTarget?.name === item.name && installTarget.version === item.version ? (
                  <div className="plugin-catalog-confirm">
                    <span>将下载并校验固定包，安装后仍需单独授权。</span>
                    <button type="button" onClick={() => void installCatalogItem(item)}>确认安装</button>
                    <button type="button" onClick={() => setInstallTarget(null)}>取消</button>
                  </div>
                ) : <button type="button" disabled={!item.installable || catalog.stale} onClick={() => setInstallTarget(item)}>
                  {item.upgrade_from ? `升级到 v${item.version}` : "安装"}
                </button>}
            </article>
          ))}
          {catalog && catalog.plugins.length === 0 && <p>当前目录没有适用于此版本的插件。</p>}
        </div>
      </section>

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
