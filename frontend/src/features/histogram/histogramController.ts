import type { HistogramData } from "./histogramModel";

export type HistogramState = Readonly<{
  status: "idle" | "updating" | "ready" | "error";
  data: HistogramData | null;
  signature: string | null;
  error: string | null;
}>;

export type HistogramController = {
  getSnapshot(): HistogramState;
  subscribe(listener: () => void): () => void;
  update(blob: Blob, signature: string): Promise<void>;
  reset(): void;
};

const INITIAL: HistogramState = Object.freeze({
  status: "idle", data: null, signature: null, error: null,
});

export function createHistogramController(
  calculate: (blob: Blob) => Promise<HistogramData>,
): HistogramController {
  let state = INITIAL;
  let generation = 0;
  const listeners = new Set<() => void>();
  const publish = (next: HistogramState) => {
    state = Object.freeze(next);
    for (const listener of listeners) listener();
  };
  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async update(blob, signature) {
      const current = ++generation;
      publish({ ...state, status: "updating", error: null });
      try {
        const data = await calculate(blob);
        if (current !== generation) return;
        publish({ status: "ready", data, signature, error: null });
      } catch (reason) {
        if (current !== generation) return;
        publish({
          ...state,
          status: "error",
          error: reason instanceof Error ? reason.message : String(reason),
        });
      }
    },
    reset() {
      generation += 1;
      publish(INITIAL);
    },
  };
}
