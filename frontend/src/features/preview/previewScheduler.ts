export type PreviewScheduler<Request> = {
  schedule(request: Request): void;
  cancel(): void;
  dispose(): void;
};

type PreviewSchedulerOptions<Request, Result> = {
  delay: number;
  execute(request: Request, signal: AbortSignal): Promise<Result>;
  onDispatch?(request: Request): void;
  onResult(result: Result, request: Request): void;
  onError?(reason: unknown, request: Request): void;
};

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

/** 防抖预览，取消过期请求，并用序号阻止旧响应覆盖新画面。 */
export function createPreviewScheduler<Request, Result>(
  options: PreviewSchedulerOptions<Request, Result>,
): PreviewScheduler<Request> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let active: AbortController | null = null;
  let sequence = 0;
  let disposed = false;

  const cancel = () => {
    sequence += 1;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    active?.abort();
    active = null;
  };

  const dispatch = async (request: Request, requestSequence: number) => {
    const controller = new AbortController();
    active = controller;
    options.onDispatch?.(request);
    try {
      const result = await options.execute(request, controller.signal);
      if (!disposed && !controller.signal.aborted && requestSequence === sequence) {
        options.onResult(result, request);
      }
    } catch (reason) {
      if (!disposed && !controller.signal.aborted && requestSequence === sequence && !isAbortError(reason)) {
        options.onError?.(reason, request);
      }
    } finally {
      if (active === controller) active = null;
    }
  };

  return {
    schedule(request) {
      if (disposed) return;
      sequence += 1;
      const requestSequence = sequence;
      if (timer !== null) clearTimeout(timer);
      active?.abort();
      timer = setTimeout(() => {
        timer = null;
        void dispatch(request, requestSequence);
      }, options.delay);
    },
    cancel,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancel();
    },
  };
}
