/// <reference lib="webworker" />
import { computeHistogram } from "./histogramModel";

self.onmessage = async (event: MessageEvent<{ id: number; blob: Blob }>) => {
  const { id, blob } = event.data;
  try {
    const bitmap = await createImageBitmap(blob);
    const scale = Math.min(1, 512 / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("无法创建直方图画布");
    context.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const result = computeHistogram(context.getImageData(0, 0, width, height).data);
    self.postMessage({ id, result });
  } catch (reason) {
    self.postMessage({ id, error: reason instanceof Error ? reason.message : String(reason) });
  }
};

export {};
