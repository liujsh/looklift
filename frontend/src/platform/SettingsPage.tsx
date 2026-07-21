import { useEffect, useState, type FormEvent } from "react";
import type { LookliftClient } from "../api/client";

export function SettingsPage({ client }: { client: LookliftClient }) {
  const [form, setForm] = useState({ provider: "auto", model: "", base_url: "", timeout: "", api_key: "" });
  const [status, setStatus] = useState("正在读取配置…");
  useEffect(() => { void client.config().then((cfg) => setForm({ provider: cfg.provider, model: cfg.model, base_url: cfg.base_url, timeout: String(cfg.timeout ?? ""), api_key: "" })).then(() => setStatus(""), () => setStatus("配置读取失败")); }, [client]);
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => { event.preventDefault(); setStatus("正在保存…"); try { await client.saveConfig({ provider: form.provider, model: form.model, base_url: form.base_url, timeout: form.timeout ? Number(form.timeout) : "", api_key: form.api_key }); setStatus("配置已保存"); } catch (error) { setStatus(error instanceof Error ? error.message : "保存失败"); } };
  return <main className="coming-soon-page settings-page" aria-label="设置与帮助"><p className="pane-kicker">SETTINGS</p><h1>设置与帮助</h1><p>配置本地 AI 模型供应商，密钥只会提交给本地引擎。</p><form onSubmit={save}><label>供应商<select value={form.provider} onChange={(e) => update("provider", e.target.value)}><option value="auto">自动选择</option><option value="cli">Claude Code CLI</option><option value="api">Anthropic API</option><option value="openai_compat">OpenAI 兼容</option><option value="ollama">Ollama</option></select></label><label>模型<input value={form.model} onChange={(e) => update("model", e.target.value)} placeholder="例如 claude-sonnet-4-20250514" /></label><label>Base URL<input value={form.base_url} onChange={(e) => update("base_url", e.target.value)} placeholder="可选" /></label><label>API Key<input type="password" value={form.api_key} onChange={(e) => update("api_key", e.target.value)} placeholder="留空则保留已保存密钥" /></label><label>超时（秒）<input value={form.timeout} onChange={(e) => update("timeout", e.target.value)} /></label><button type="submit">保存模型配置</button></form>{status && <span role="status">{status}</span>}</main>;
}
