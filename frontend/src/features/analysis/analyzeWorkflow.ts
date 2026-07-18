import type { LookliftClient } from "../../api/client";
import type { Analysis } from "../../api/types";

type AnalyzeClient = Pick<LookliftClient, "analyze" | "task">;

type AnalyzeOptions = {
  pollInterval?: number;
  signal?: AbortSignal;
};

function isAnalysis(value: unknown): value is Analysis {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Analysis>;
  return typeof candidate.summary === "string"
    && Array.isArray(candidate.steps)
    && Boolean(candidate.basic && typeof candidate.basic === "object")
    && Array.isArray(candidate.tone_curve)
    && Array.isArray(candidate.hsl)
    && Boolean(candidate.color_grading && typeof candidate.color_grading === "object")
    && Boolean(candidate.effects && typeof candidate.effects === "object");
}

function abortError(): DOMException {
  return new DOMException("AI 分析已取消", "AbortError");
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(done, ms);
    function done() {
      signal?.removeEventListener("abort", cancelled);
      resolve();
    }
    function cancelled() {
      clearTimeout(timer);
      reject(abortError());
    }
    signal?.addEventListener("abort", cancelled, { once: true });
  });
}

export async function analyzeImage(
  client: AnalyzeClient,
  path: string,
  { pollInterval = 500, signal }: AnalyzeOptions = {},
): Promise<Analysis> {
  if (signal?.aborted) throw abortError();
  const { task_id: taskId } = await client.analyze({ path });
  while (true) {
    if (signal?.aborted) throw abortError();
    const task = await client.task(taskId);
    if (task.status === "error") throw new Error(task.error ?? "AI 分析失败");
    if (task.status === "done") {
      if (!isAnalysis(task.result)) throw new Error("AI 分析完成，但没有返回参数结果");
      return task.result;
    }
    await wait(pollInterval, signal);
  }
}
