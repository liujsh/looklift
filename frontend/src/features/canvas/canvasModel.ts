import type { Analysis } from "../../api/types";

export const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"] as const;

export type CanvasApi = {
  preview(payload: { path: string; analysis: Analysis; factor: number }): Promise<Blob>;
  upload(file: File): Promise<{ path: string }>;
};

export type PreviewPair = { before: Blob; after: Blob };

export function firstSupportedImage(paths: string[]): string | null {
  return paths.find((path) => {
    const lower = path.toLowerCase();
    return IMAGE_EXTENSIONS.some((extension) => lower.endsWith(extension));
  }) ?? null;
}

export async function loadPreviewPair(
  client: CanvasApi,
  path: string,
  analysis: Analysis,
  factor: number,
): Promise<PreviewPair> {
  const [before, after] = await Promise.all([
    client.preview({ path, analysis, factor: 0 }),
    client.preview({ path, analysis, factor }),
  ]);
  return { before, after };
}

export function canvasErrorMessage(reason: unknown): string {
  if (reason instanceof Error && reason.message) return reason.message;
  return `无法载入照片：${String(reason)}`;
}
