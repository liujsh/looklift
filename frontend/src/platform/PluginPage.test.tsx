// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import { PluginPage } from "./PluginPage";

const plugin = {
  id: "notes",
  version: "1.0.0",
  kind: "connector",
  task_kind: "notes",
  mode: "sidecar",
  inputs: ["text"],
  capabilities: ["notes.read"],
  granted_capabilities: [],
  content_hash: "a".repeat(64),
  source: "catalog",
  enabled: true,
  installed: true,
  services: [{
    name: "main",
    transport: "stdio",
    requires_credential: true,
  }],
};

const connection = {
  connector_id: "pc-notes",
  protocol: "mcp",
  receiver: "notes",
  capabilities: ["notes.read"],
  workspace_id: "default-project",
  account_id: "work",
  authorized: true,
  connected: false,
  plugin_name: "notes",
  plugin_version: "1.0.0",
  service: "main",
};

const catalog = {
  revision: 7,
  issued_at: 1_000,
  expires_at: 2_000,
  stale: false,
  plugins: [{
    name: "notes",
    version: "2.0.0",
    license: "MIT",
    capabilities: ["notes.read", "notes.write"],
    platforms: ["win32"],
    compatible: true,
    installed: false,
    enabled: false,
    package_present: false,
    revoked: false,
    installable: true,
    upgrade_from: "1.0.0",
  }],
};

describe("PluginPage", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  function client(overrides = {}) {
    return {
      plugins: vi.fn().mockResolvedValue([plugin]),
      pluginCatalog: vi.fn().mockResolvedValue(catalog),
      refreshPluginCatalog: vi.fn().mockResolvedValue(catalog),
      installCatalogPlugin: vi.fn().mockResolvedValue({ name: "notes", version: "2.0.0", installed: true }),
      pluginConnectors: vi.fn().mockResolvedValue([connection]),
      pluginActions: vi.fn().mockResolvedValue([]),
      grantPlugin: vi.fn().mockResolvedValue(plugin),
      revokePlugin: vi.fn().mockResolvedValue(plugin),
      setPluginEnabled: vi.fn().mockResolvedValue({ ok: true }),
      cleanupPlugin: vi.fn().mockResolvedValue({ ok: true }),
      createPluginConnector: vi.fn().mockResolvedValue(connection),
      connectPluginConnector: vi.fn().mockResolvedValue({ ...connection, connected: true, tools: 1 }),
      disconnectPluginConnector: vi.fn().mockResolvedValue(connection),
      forgetPluginConnector: vi.fn().mockResolvedValue({ ...connection, authorized: false }),
      ...overrides,
    } as unknown as LookliftClient;
  }

  async function fill(input: HTMLInputElement, value: string) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  it("按项目同时加载授权与账号连接", async () => {
    const current = client();
    await act(async () => root.render(<PluginPage client={current} />));

    await vi.waitFor(() => expect(container.textContent).toContain("账号连接"));
    expect(current.plugins).toHaveBeenCalledWith("default-project", true);
    expect(current.pluginConnectors).toHaveBeenCalledWith("default-project");
    expect(current.pluginActions).toHaveBeenCalledWith("default-project");
    expect(container.textContent).toContain("work");
    expect(container.textContent).toContain("未连接");
    expect(container.textContent).toContain("官方精选目录");
  });

  it("目录升级安装前展示能力并要求二次确认", async () => {
    const installCatalogPlugin = vi.fn().mockResolvedValue({ name: "notes", version: "2.0.0", installed: true });
    const current = client({ installCatalogPlugin });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("升级到 v2.0.0"));

    const upgrade = [...container.querySelectorAll("button")].find((item) => item.textContent === "升级到 v2.0.0")!;
    await act(async () => upgrade.click());
    expect(installCatalogPlugin).not.toHaveBeenCalled();
    expect(container.textContent).toContain("notes.write");
    const confirm = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认安装")!;
    await act(async () => confirm.click());

    await vi.waitFor(() => expect(installCatalogPlugin).toHaveBeenCalledWith("notes", "2.0.0"));
  });

  it("只有显式确认后才创建连接，且不回显凭据", async () => {
    const createPluginConnector = vi.fn().mockResolvedValue(connection);
    const current = client({ createPluginConnector });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("notes"));

    const open = [...container.querySelectorAll("button")].find((item) => item.textContent === "连接账号")!;
    await act(async () => open.click());
    await fill(container.querySelector('input[name="account_id"]') as HTMLInputElement, "work-account");
    await fill(container.querySelector('input[name="credential"]') as HTMLInputElement, "top-secret");
    const confirm = container.querySelector('input[name="confirmed"]') as HTMLInputElement;
    await act(async () => confirm.click());
    const submit = [...container.querySelectorAll("button")].find((item) => item.textContent === "保存连接")!;
    await act(async () => submit.click());

    await vi.waitFor(() => expect(createPluginConnector).toHaveBeenCalledWith({
      plugin_name: "notes",
      version: "1.0.0",
      service_name: "main",
      project_id: "default-project",
      account_id: "work-account",
      credential: "top-secret",
      confirmed: true,
    }));
    expect(container.querySelector('input[name="credential"]')).toBeNull();
    expect(container.textContent).not.toContain("top-secret");
  });

  it("连接生命周期始终携带当前项目", async () => {
    const connectPluginConnector = vi.fn().mockResolvedValue({ ...connection, connected: true, tools: 1 });
    const forgetPluginConnector = vi.fn().mockResolvedValue({ ...connection, authorized: false });
    const current = client({ connectPluginConnector, forgetPluginConnector });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("未连接"));

    const connect = [...container.querySelectorAll("button")].find((item) => item.textContent === "连接")!;
    await act(async () => connect.click());
    await vi.waitFor(() => expect(connectPluginConnector).toHaveBeenCalledWith("pc-notes", "default-project"));

    const forget = [...container.querySelectorAll("button")].find((item) => item.textContent === "忘记账号")!;
    await act(async () => forget.click());
    expect(forgetPluginConnector).not.toHaveBeenCalled();
    const confirmForget = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认忘记")!;
    await act(async () => confirmForget.click());
    await vi.waitFor(() => expect(forgetPluginConnector).toHaveBeenCalledWith("pc-notes", "default-project"));
  });

  it("停用精确版本前要求二次确认", async () => {
    const setPluginEnabled = vi.fn().mockResolvedValue({ ok: true });
    const current = client({ setPluginEnabled });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("停用"));

    const disable = [...container.querySelectorAll("button")].find((item) => item.textContent === "停用")!;
    await act(async () => disable.click());
    expect(setPluginEnabled).not.toHaveBeenCalled();
    const confirm = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认停用")!;
    await act(async () => confirm.click());

    await vi.waitFor(() => expect(setPluginEnabled).toHaveBeenCalledWith("notes", "1.0.0", false));
  });

  it("已停用版本保留账号审计但不能重新连接", async () => {
    const current = client({ plugins: vi.fn().mockResolvedValue([{ ...plugin, enabled: false }]) });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("已禁用"));

    const connect = [...container.querySelectorAll("button")].find((item) => item.textContent === "连接")!;
    expect(connect.disabled).toBe(true);
    expect(connect.title).toBe("对应插件版本已停用");
    expect(container.textContent).toContain("work");
  });

  it("已停用版本清理包前要求二次确认", async () => {
    const cleanupPlugin = vi.fn().mockResolvedValue({ ok: true });
    const current = client({
      plugins: vi.fn().mockResolvedValue([{ ...plugin, enabled: false }]),
      cleanupPlugin,
    });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("清理包"));

    const cleanup = [...container.querySelectorAll("button")].find((item) => item.textContent === "清理包")!;
    await act(async () => cleanup.click());
    expect(cleanupPlugin).not.toHaveBeenCalled();
    const confirm = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认清理")!;
    await act(async () => confirm.click());

    await vi.waitFor(() => expect(cleanupPlugin).toHaveBeenCalledWith("notes", "1.0.0"));
  });

  it("包已清理版本只保留历史，不允许重新启用", async () => {
    const current = client({
      plugins: vi.fn().mockResolvedValue([{ ...plugin, enabled: false, installed: false }]),
    });
    await act(async () => root.render(<PluginPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("包已清理"));

    expect([...container.querySelectorAll("button")].some((item) => item.textContent === "重新启用")).toBe(false);
    expect([...container.querySelectorAll("button")].some((item) => item.textContent === "清理包")).toBe(false);
  });
});
