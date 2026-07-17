import type { LookliftClient } from "../../api/client";
import type { Analysis, LookSummary } from "../../api/types";

type SaveClient = Pick<LookliftClient, "saveLook" | "listLooks">;
type ExportClient = Pick<LookliftClient, "exportLook">;
type ReportClient = Pick<LookliftClient, "reportUrl">;

export async function saveCurrentLook(
  client: SaveClient,
  rawName: string,
  analysis: Analysis,
  factor: number,
): Promise<{ name: string; looks: LookSummary[] }> {
  const name = rawName.trim();
  if (!name) throw new Error("请输入风格名称");
  const saved = await client.saveLook({ name, analysis, factor });
  return { name: saved.name, looks: await client.listLooks() };
}

export function openLookReport(
  client: ReportClient,
  name: string,
  open: (url: string, target: string, features: string) => unknown = window.open,
): void {
  open(client.reportUrl(name), "_blank", "noopener,noreferrer");
}

export async function exportLookFile(
  client: ExportClient,
  name: string,
  sidecar?: string,
): Promise<string> {
  const payload = sidecar ? { sidecar } : {};
  const result = await client.exportLook(name, payload);
  const path = result.preset ?? result.sidecar;
  if (typeof path !== "string" || !path) throw new Error("导出完成，但未返回文件路径");
  return path;
}
