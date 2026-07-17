import { afterEach, describe, expect, it, vi } from "vitest";
import { createPreviewScheduler } from "./previewScheduler";

type Deferred<T> = {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

afterEach(() => vi.useRealTimers());

describe("previewScheduler", () => {
  it("连续变化只在最后一次静止 160ms 后发出请求", async () => {
    vi.useFakeTimers();
    const execute = vi.fn(async (value: number) => value * 2);
    const results: number[] = [];
    const scheduler = createPreviewScheduler({
      delay: 160,
      execute,
      onResult: (result) => results.push(result),
    });

    scheduler.schedule(1);
    await vi.advanceTimersByTimeAsync(100);
    scheduler.schedule(2);
    await vi.advanceTimersByTimeAsync(159);
    expect(execute).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0][0]).toBe(2);
    expect(results).toEqual([4]);
  });

  it("新请求取消旧信号，旧慢响应即使随后完成也不能覆盖新结果", async () => {
    vi.useFakeTimers();
    const first = deferred<string>();
    const second = deferred<string>();
    const signals: AbortSignal[] = [];
    const results: string[] = [];
    const scheduler = createPreviewScheduler<number, string>({
      delay: 160,
      execute: (value, signal) => {
        signals.push(signal);
        return value === 1 ? first.promise : second.promise;
      },
      onResult: (result) => results.push(result),
    });

    scheduler.schedule(1);
    await vi.advanceTimersByTimeAsync(160);
    scheduler.schedule(2);
    expect(signals[0].aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(160);

    first.resolve("旧图");
    await Promise.resolve();
    expect(results).toEqual([]);
    second.resolve("新图");
    await Promise.resolve();
    await Promise.resolve();
    expect(results).toEqual(["新图"]);
  });

  it("dispose 清除待发任务并取消在途请求", async () => {
    vi.useFakeTimers();
    const running = deferred<string>();
    let signal: AbortSignal | undefined;
    const execute = vi.fn((_value: number, nextSignal: AbortSignal) => {
      signal = nextSignal;
      return running.promise;
    });
    const scheduler = createPreviewScheduler({ delay: 160, execute, onResult: () => undefined });

    scheduler.schedule(1);
    await vi.advanceTimersByTimeAsync(160);
    scheduler.dispose();
    expect(signal?.aborted).toBe(true);

    scheduler.schedule(2);
    await vi.advanceTimersByTimeAsync(200);
    expect(execute).toHaveBeenCalledTimes(1);
  });

  it("cancel 取消当前图片请求，但调度器仍可服务下一张图片", async () => {
    vi.useFakeTimers();
    const first = deferred<string>();
    const signals: AbortSignal[] = [];
    const results: string[] = [];
    const scheduler = createPreviewScheduler<number, string>({
      delay: 160,
      execute: (value, signal) => {
        signals.push(signal);
        return value === 1 ? first.promise : Promise.resolve("新图");
      },
      onResult: (result) => results.push(result),
    });

    scheduler.schedule(1);
    await vi.advanceTimersByTimeAsync(160);
    scheduler.cancel();
    expect(signals[0].aborted).toBe(true);

    scheduler.schedule(2);
    await vi.advanceTimersByTimeAsync(160);
    expect(results).toEqual(["新图"]);
  });
});
