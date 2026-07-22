import { describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { LibraryScanTask } from "../api/types";
import { waitForLibraryScan } from "./libraryWorkflow";

const running: LibraryScanTask = {
  status: "running", message: "已扫描 1 个文件", result: null, error: null,
  scanned: 1, current: "a.jpg",
};
const done: LibraryScanTask = {
  status: "done", message: null, result: { added: 1, updated: 0, missing: 0 }, error: null,
  scanned: 1, current: null,
};

describe("waitForLibraryScan", () => {
  it("持续轮询到终态并上报每次进度", async () => {
    const libraryScan = vi.fn().mockResolvedValueOnce(running).mockResolvedValueOnce(done);
    const progress = vi.fn();

    await expect(waitForLibraryScan(
      { libraryScan } as unknown as LookliftClient,
      "scan-1",
      progress,
      undefined,
      0,
    )).resolves.toEqual(done);

    expect(progress).toHaveBeenCalledTimes(2);
    expect(libraryScan).toHaveBeenCalledTimes(2);
  });

  it("外部取消后停止继续轮询", async () => {
    const controller = new AbortController();
    controller.abort();
    const libraryScan = vi.fn();

    await expect(waitForLibraryScan(
      { libraryScan } as unknown as LookliftClient,
      "scan-1",
      vi.fn(),
      controller.signal,
      0,
    )).rejects.toMatchObject({ name: "AbortError" });
    expect(libraryScan).not.toHaveBeenCalled();
  });
});
