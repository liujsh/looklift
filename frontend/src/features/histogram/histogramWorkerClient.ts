import type { HistogramData } from "./histogramModel";

let nextId = 0;

export function calculateHistogramInWorker(blob: Blob): Promise<HistogramData> {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const worker = new Worker(new URL("./histogramWorker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<{ id: number; result?: HistogramData; error?: string }>) => {
      if (event.data.id !== id) return;
      worker.terminate();
      if (event.data.result) resolve(event.data.result);
      else reject(new Error(event.data.error ?? "直方图计算失败"));
    };
    worker.onerror = () => {
      worker.terminate();
      reject(new Error("直方图计算失败"));
    };
    worker.postMessage({ id, blob });
  });
}
