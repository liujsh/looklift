import type { LookliftClient } from "../api/client";
import type { AutomationRun } from "../api/types";

export async function waitForAutomationRun(
  client: Pick<LookliftClient, "automationRun">,
  runId: string,
  onProgress: (run: AutomationRun) => void,
  signal?: AbortSignal,
  delayMs = 300,
): Promise<AutomationRun> {
  while (true) {
    if (signal?.aborted) throw new DOMException("轮询已取消", "AbortError");
    const run = await client.automationRun(runId);
    onProgress(run);
    if (run.status !== "running") return run;
    await delay(delayMs, signal);
  }
}

function delay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (milliseconds <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const finish = () => {
      signal?.removeEventListener("abort", abort);
      resolve();
    };
    const abort = () => {
      globalThis.clearTimeout(timer);
      reject(new DOMException("轮询已取消", "AbortError"));
    };
    const timer = globalThis.setTimeout(finish, milliseconds);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
