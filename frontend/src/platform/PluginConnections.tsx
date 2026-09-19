import { useEffect, useMemo, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { PluginConnectorSummary, PluginSummary } from "../api/types";
import { Icon } from "./icons";

type Props = {
  client: LookliftClient;
  projectId: string;
  plugins: PluginSummary[];
  targetId: string | null;
  onTargetChange: (id: string | null) => void;
};

function message(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

export function PluginConnections({ client, projectId, plugins, targetId, onTargetChange }: Props) {
  const [connections, setConnections] = useState<PluginConnectorSummary[]>([]);
  const [status, setStatus] = useState("正在读取账号连接…");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [accountId, setAccountId] = useState("default");
  const [serviceName, setServiceName] = useState("");
  const [credential, setCredential] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [forgetId, setForgetId] = useState<string | null>(null);
  const target = useMemo(
    () => plugins.find((plugin) => `${plugin.id}@${plugin.version}` === targetId) ?? null,
    [plugins, targetId],
  );
  const service = target?.services.find((item) => item.name === serviceName)
    ?? target?.services[0]
    ?? null;

  const refresh = async () => {
    setConnections(await client.pluginConnectors(projectId));
  };

  useEffect(() => {
    let active = true;
    setStatus("正在读取账号连接…");
    client.pluginConnectors(projectId).then(
      (items) => {
        if (!active) return;
        setConnections(items);
        setStatus("");
      },
      (reason) => {
        if (active) setStatus(message(reason, "账号连接读取失败"));
      },
    );
    return () => { active = false; };
  }, [client, projectId]);

  useEffect(() => {
    if (!target) return;
    setServiceName(target.services[0]?.name ?? "");
    setAccountId("default");
    setCredential("");
    setConfirmed(false);
  }, [target]);

  const create = async () => {
    if (!target || !service || !confirmed) return;
    setBusyId("create");
    setStatus("正在保存账号连接…");
    try {
      await client.createPluginConnector({
        plugin_name: target.id,
        version: target.version,
        service_name: service.name,
        project_id: projectId,
        account_id: accountId,
        ...(service.requires_credential ? { credential } : {}),
        confirmed: true,
      });
      await refresh();
      setCredential("");
      onTargetChange(null);
      setStatus("账号连接已保存，连接前仍会重新完成 MCP 握手");
    } catch (reason) {
      setStatus(message(reason, "账号连接保存失败"));
    } finally {
      setBusyId(null);
    }
  };

  const run = async (connection: PluginConnectorSummary, action: "connect" | "disconnect" | "forget") => {
    setBusyId(connection.connector_id);
    setStatus(action === "forget" ? "正在撤权并清理账号…" : "正在更新连接状态…");
    try {
      if (action === "connect") await client.connectPluginConnector(connection.connector_id, projectId);
      if (action === "disconnect") await client.disconnectPluginConnector(connection.connector_id, projectId);
      if (action === "forget") await client.forgetPluginConnector(connection.connector_id, projectId);
      await refresh();
      setForgetId(null);
      setStatus(action === "forget" ? "账号凭据与 Profile 已清理" : "连接状态已更新");
    } catch (reason) {
      setStatus(message(reason, "连接操作失败"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="plugin-connections" aria-labelledby="plugin-connections-title">
      <header>
        <div>
          <h2 id="plugin-connections-title">账号连接</h2>
          <p>连接状态属于当前项目。普通断开保留登录信息，忘记账号会撤权并清理本机凭据。</p>
        </div>
        <span>{connections.length} 个账号</span>
      </header>

      {status && <p role="status" className="plugin-inline-status">{status}</p>}

      {target && service && (
        <form className="connector-create" onSubmit={(event) => { event.preventDefault(); void create(); }}>
          <header>
            <div>
              <strong>连接 {target.id}</strong>
              <span>v{target.version}</span>
            </div>
            <button type="button" aria-label="关闭连接表单" onClick={() => onTargetChange(null)}><Icon name="close" /></button>
          </header>
          <div className="connector-fields">
            {target.services.length > 1 && (
              <label>服务
                <select value={service.name} onChange={(event) => setServiceName(event.target.value)}>
                  {target.services.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
                </select>
              </label>
            )}
            <label>账号标识
              <input name="account_id" required pattern="[a-z0-9][a-z0-9_-]{0,63}" value={accountId} onChange={(event) => setAccountId(event.target.value)} />
              <small>只用于本机区分账号，不发送给模型。</small>
            </label>
            {service.requires_credential && (
              <label>账号凭据
                <input name="credential" type="password" required autoComplete="off" value={credential} onChange={(event) => setCredential(event.target.value)} />
                <small>仅写入 Windows DPAPI，不保存到 Plugin 配置。</small>
              </label>
            )}
          </div>
          <label className="connector-confirm">
            <input name="confirmed" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            我确认将此账号授权给 {target.id} 的 {service.name} 服务
          </label>
          <div className="connector-form-actions">
            <button type="submit" disabled={!confirmed || busyId === "create"}>保存连接</button>
            <button type="button" onClick={() => onTargetChange(null)}>取消</button>
          </div>
        </form>
      )}

      <div className="connector-list">
        {connections.map((connection) => (
          <article key={connection.connector_id} className="connector-row">
            <span className="connector-mark" aria-hidden="true"><Icon name="server" /></span>
            <div>
              <strong>{connection.account_id}</strong>
              <span>{connection.plugin_name} / {connection.service}</span>
            </div>
            <span className={`connector-state ${connection.connected ? "connected" : ""}`}>
              {connection.connected ? "已连接" : "未连接"}
            </span>
            <div className="connector-actions">
              <button
                type="button"
                disabled={busyId === connection.connector_id || !plugins.some((plugin) => plugin.id === connection.plugin_name && plugin.version === connection.plugin_version && plugin.enabled)}
                title={!plugins.some((plugin) => plugin.id === connection.plugin_name && plugin.version === connection.plugin_version && plugin.enabled) ? "对应插件版本已停用" : undefined}
                onClick={() => void run(connection, connection.connected ? "disconnect" : "connect")}
              >
                {connection.connected ? "断开" : "连接"}
              </button>
              {forgetId === connection.connector_id ? (
                <>
                  <button type="button" className="danger" disabled={busyId === connection.connector_id} onClick={() => void run(connection, "forget")}>确认忘记</button>
                  <button type="button" onClick={() => setForgetId(null)}>取消</button>
                </>
              ) : (
                <button type="button" className="quiet-danger" onClick={() => setForgetId(connection.connector_id)}>忘记账号</button>
              )}
            </div>
          </article>
        ))}
        {connections.length === 0 && !status && (
          <div className="connector-empty">
            <Icon name="lock" />
            <span>当前项目还没有账号连接。请从上方已审核的 Connector Plugin 开始。</span>
          </div>
        )}
      </div>
    </section>
  );
}
