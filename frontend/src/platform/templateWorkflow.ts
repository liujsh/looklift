import type { LookliftClient } from "../api/client";
import type { StudioRuntime } from "./studioRuntime";

export async function applyTemplateToStudio(
  client: Pick<LookliftClient, "getLook">,
  runtime: Pick<StudioRuntime, "store" | "coordinator">,
  name: string,
): Promise<void> {
  const analysis = await client.getLook(name);
  runtime.store.setFactor(1);
  if (!runtime.store.commitAnalysis(analysis, "library")) {
    throw new Error("Studio 正在处理其他修改，请稍后重试");
  }
  await runtime.coordinator.commitFormal(analysis, "library");
}
