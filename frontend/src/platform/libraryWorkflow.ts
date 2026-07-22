import type { LookliftClient } from "../api/client";
import type { LibraryScanTask } from "../api/types";

export async function waitForLibraryScan(
  client: Pick<LookliftClient, "libraryScan">,
  taskId: string,
  onProgress: (task: LibraryScanTask) => void,
  signal?: AbortSignal,
  delayMs = 300,
): Promise<LibraryScanTask> {
  while (true) {
    if (signal?.aborted) throw new DOMException("轮询已取消", "AbortError");
    const task = await client.libraryScan(taskId);
    onProgress(task);
    if (task.status !== "running") return task;
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
