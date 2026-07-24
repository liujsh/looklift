import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { LookliftClient } from "../api/client";
import type {
  AutomationPlan,
  AutomationRun,
  AutomationWorkflow,
  LookSummary,
} from "../api/types";
import { waitForAutomationRun } from "./automationWorkflow";
import { AutomationRunCard } from "./AutomationRunCard";

type AutomationPageProps = {
  client: LookliftClient;
  chooseInputs?: () => Promise<string[]>;
  chooseOutput?: () => Promise<string | null>;
};

const IMAGE_FILTERS = [{
  name: "照片",
  extensions: ["jpg", "jpeg", "png", "webp", "tif", "tiff"],
}];

export function AutomationPage({ client, chooseInputs, chooseOutput }: AutomationPageProps) {
  const [looks, setLooks] = useState<LookSummary[]>([]);
  const [workflows, setWorkflows] = useState<AutomationWorkflow[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [inputs, setInputs] = useState<string[]>([]);
  const [outputDir, setOutputDir] = useState("");
  const [plan, setPlan] = useState<AutomationPlan | null>(null);
  const [run, setRun] = useState<AutomationRun | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const polling = useRef<AbortController | null>(null);
  const [draft, setDraft] = useState({
    name: "",
    look_name: "",
    factor: 100,
    suffix: "-looklift",
    quality: 92,
  });

  const selected = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedId) ?? null,
    [selectedId, workflows],
  );

  const load = async () => {
    const [nextLooks, nextWorkflows, nextRuns] = await Promise.all([
      client.listLooks(),
      client.listAutomationWorkflows(),
      client.listAutomationRuns(),
    ]);
    setLooks(nextLooks);
    setWorkflows(nextWorkflows);
    setRuns(nextRuns);
    setSelectedId((current) => current || nextWorkflows[0]?.id || "");
    setDraft((current) => ({ ...current, look_name: current.look_name || nextLooks[0]?.name || "" }));
  };

  useEffect(() => {
    void load().catch((reason) => setError(message(reason, "自动化数据读取失败")));
    return () => {
      polling.current?.abort();
    };
  }, []);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const clearPlan = () => {
    setPlan(null);
    setRun(null);
    setPreviewUrl(null);
  };

  const createWorkflow = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const created = await client.createAutomationWorkflow({
        name: draft.name,
        look_name: draft.look_name,
        factor: draft.factor / 100,
        suffix: draft.suffix,
        quality: draft.quality,
      });
      const next = await client.listAutomationWorkflows();
      setWorkflows(next);
      setSelectedId(created.id);
      setDraft((current) => ({ ...current, name: "" }));
      clearPlan();
    } catch (reason) {
      setError(message(reason, "创建技能失败"));
    }
  };

  const removeWorkflow = async () => {
    if (!selected) return;
    try {
      await client.deleteAutomationWorkflow(selected.id);
      const next = await client.listAutomationWorkflows();
      setWorkflows(next);
      setSelectedId(next[0]?.id ?? "");
      clearPlan();
    } catch (reason) {
      setError(message(reason, "删除技能失败"));
    }
  };

  const pickInputs = async () => {
    try {
      let selectedPaths: string[];
      if (chooseInputs) {
        selectedPaths = await chooseInputs();
      } else {
        if (!isTauri()) throw new Error("浏览器开发模式不能读取本地文件路径");
        const selectedFiles = await open({ multiple: true, directory: false, filters: IMAGE_FILTERS, title: "选择批量照片" });
        selectedPaths = selectedFiles ? (Array.isArray(selectedFiles) ? selectedFiles : [selectedFiles]) : [];
      }
      if (selectedPaths.length) {
        setInputs(selectedPaths);
        clearPlan();
      }
    } catch (reason) {
      setError(message(reason, "选择照片失败"));
    }
  };

  const pickOutput = async () => {
    try {
      let selectedPath: string | null;
      if (chooseOutput) {
        selectedPath = await chooseOutput();
      } else {
        if (!isTauri()) throw new Error("浏览器开发模式不能读取本地目录");
        const chosen = await open({ multiple: false, directory: true, title: "选择成片输出目录" });
        selectedPath = typeof chosen === "string" ? chosen : null;
      }
      if (selectedPath) {
        setOutputDir(selectedPath);
        clearPlan();
      }
    } catch (reason) {
      setError(message(reason, "选择输出目录失败"));
    }
  };

  const buildPlan = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    clearPlan();
    try {
      const nextPlan = await client.planAutomation({
        workflow_id: selected.id,
        inputs,
        output_dir: outputDir,
      });
      setPlan(nextPlan);
      const first = nextPlan.items.find((item) => item.status === "ready");
      if (first) {
        try {
          const analysis = await client.getLook(selected.look_name);
          const blob = await client.preview({
            path: first.source,
            analysis,
            factor: selected.factor,
          });
          setPreviewUrl(URL.createObjectURL(blob));
        } catch (reason) {
          setError(message(reason, "首张照片无法预览；可调整输入，或执行后在失败项中查看原因"));
        }
      }
    } catch (reason) {
      setError(message(reason, "生成执行计划失败"));
    } finally {
      setBusy(false);
    }
  };

  const follow = async (runId: string) => {
    polling.current?.abort();
    const controller = new AbortController();
    polling.current = controller;
    try {
      const finished = await waitForAutomationRun(client, runId, setRun, controller.signal);
      setRun(finished);
      setRuns(await client.listAutomationRuns());
    } finally {
      if (polling.current === controller) polling.current = null;
    }
  };

  const execute = async () => {
    if (!plan?.ready) return;
    setBusy(true);
    setError("");
    try {
      const started = await client.startAutomationRun(plan.id);
      await follow(started.run_id);
    } catch (reason) {
      setError(message(reason, "自动化执行失败"));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!run || run.status !== "running") return;
    try {
      await client.cancelAutomationRun(run.id);
    } catch (reason) {
      setError(message(reason, "取消任务失败"));
    }
  };

  const retry = async () => {
    if (!run) return;
    setBusy(true);
    try {
      const started = await client.retryAutomationRun(run.id);
      await follow(started.run_id);
    } catch (reason) {
      setError(message(reason, "重试失败项失败"));
    } finally {
      setBusy(false);
    }
  };

  return <main className="automation-page" aria-label="自动化技能">
    <header className="automation-heading">
      <div><p className="pane-kicker">WHITE-BOX AUTOMATION</p><h1>自动化技能</h1></div>
      <p>先预览、再确认；批量成片只写新文件，不改变原照片。</p>
    </header>
    {error && <div className="automation-message error" role="alert">{error}</div>}

    <section className="automation-section">
      <div className="automation-section-title"><h2>1. 保存常用技能</h2><span>已有风格 + 明确输出规则</span></div>
      <form className="automation-workflow-form" onSubmit={createWorkflow}>
        <input aria-label="技能名称" required placeholder="例如：旅行胶片批处理" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
        <select aria-label="引用风格" required value={draft.look_name} onChange={(event) => setDraft({ ...draft, look_name: event.target.value })}>
          {looks.map((look) => <option key={look.name} value={look.name}>{look.name}</option>)}
        </select>
        <label>强度 <input type="number" min="0" max="100" value={draft.factor} onChange={(event) => setDraft({ ...draft, factor: Number(event.target.value) })} />%</label>
        <label>后缀 <input required value={draft.suffix} onChange={(event) => setDraft({ ...draft, suffix: event.target.value })} /></label>
        <label>JPEG 质量 <input type="number" min="60" max="100" value={draft.quality} onChange={(event) => setDraft({ ...draft, quality: Number(event.target.value) })} /></label>
        <button type="submit">保存技能</button>
      </form>
      <div className="automation-workflow-select">
        <select aria-label="选择自动化技能" value={selectedId} onChange={(event) => { setSelectedId(event.target.value); clearPlan(); }}>
          <option value="">选择一个技能</option>
          {workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name} · {workflow.look_name}</option>)}
        </select>
        <button type="button" disabled={!selected} onClick={() => void removeWorkflow()}>删除技能</button>
      </div>
    </section>

    <section className="automation-section">
      <div className="automation-section-title"><h2>2. 选择照片并预览计划</h2><span>执行前不会创建任何成片</span></div>
      <div className="automation-pickers">
        <button type="button" onClick={() => void pickInputs()}>选择照片</button>
        <span>{inputs.length ? `已选择 ${inputs.length} 张` : "尚未选择照片"}</span>
        <button type="button" onClick={() => void pickOutput()}>选择输出目录</button>
        <span title={outputDir}>{outputDir || "尚未选择输出目录"}</span>
        <button className="primary" type="button" disabled={!selected || !inputs.length || !outputDir || busy} onClick={() => void buildPlan()}>
          {busy && !run ? "正在生成…" : "生成预览计划"}
        </button>
      </div>
      {plan && <div className="automation-plan" data-ready={plan.ready}>
        <div className="automation-preview">
          {previewUrl ? <img src={previewUrl} alt="首张应用技能后的效果预览" /> : <div>没有可预览的有效照片</div>}
          <strong>{plan.ready ? "计划可以执行" : "请先解决计划中的冲突"}</strong>
        </div>
        <div className="automation-plan-items">
          {plan.items.map((item) => <div key={`${item.source}:${item.output}`} data-status={item.status}>
            <span title={item.source}>{fileName(item.source)}</span>
            <span aria-hidden="true">→</span>
            <span title={item.output}>{fileName(item.output)}</span>
            <small>{item.error ?? "准备就绪"}</small>
          </div>)}
        </div>
        <button className="primary" type="button" disabled={!plan.ready || busy} onClick={() => void execute()}>确认并开始批量成片</button>
      </div>}
    </section>

    {(run || runs.length > 0) && <section className="automation-section">
      <div className="automation-section-title"><h2>3. 运行结果</h2><span>记录保存在本机，可恢复失败项</span></div>
      {run && <AutomationRunCard run={run} active onCancel={cancel} onRetry={retry} busy={busy} />}
      {!run && runs.slice(0, 5).map((item) => <AutomationRunCard run={item} key={item.id} onSelect={() => setRun(item)} />)}
    </section>}
  </main>;
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}
