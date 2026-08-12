import type { LookliftClient } from "../api/client";
import type { SessionSnapshot } from "../api/types";
import type { StudioRuntime } from "./studioRuntime";

const TEMPLATE_APPLY_LOCK_ID = Number.MAX_SAFE_INTEGER;

export async function applyTemplateToStudio(
  client: Pick<LookliftClient, "getLook">,
  runtime: Pick<StudioRuntime, "store" | "coordinator">,
  name: string,
): Promise<void> {
  assertTemplateApplicable(runtime);
  const analysis = await client.getLook(name);
  assertTemplateApplicable(runtime);
  if (!runtime.store.beginAiRequest(TEMPLATE_APPLY_LOCK_ID)) {
    throw new Error("Studio 正在处理其他修改，请稍后重试");
  }
  let persisted: SessionSnapshot;
  try {
    persisted = await runtime.coordinator.commitFormal(analysis, "library");
  } finally {
    runtime.store.endAiRequest(TEMPLATE_APPLY_LOCK_ID);
  }
  runtime.store.setFactor(1);
  if (!runtime.store.commitAnalysis(persisted.current_analysis, "library")) {
    throw new Error("Studio 正在处理其他修改，请稍后重试");
  }
}

export function canApplyTemplateToStudio(runtime: Pick<StudioRuntime, "store">): boolean {
  const state = runtime.store.getSnapshot();
  return state.activeAiRequestId === null && state.pendingPreview === null;
}

function assertTemplateApplicable(runtime: Pick<StudioRuntime, "store">): void {
  const state = runtime.store.getSnapshot();
  if (state.activeAiRequestId !== null) throw new Error("Studio 正在处理AI 修改，请稍后重试");
  if (state.pendingPreview !== null) throw new Error("Studio 正在处理待确认版本，请先保留或撤销");
}
