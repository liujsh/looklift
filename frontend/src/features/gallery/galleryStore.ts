import type { LookliftClient } from "../../api/client";
import type { Analysis, LookSummary } from "../../api/types";

export type GallerySource = LookSummary["source"];

export function looksForSource(
  looks: readonly LookSummary[],
  source: GallerySource,
): LookSummary[] {
  return looks.filter((look) => look.source === source);
}

export async function loadLookIntoEditor(
  client: Pick<LookliftClient, "getLook">,
  name: string,
  commit: (analysis: Analysis) => void,
): Promise<Analysis> {
  const analysis = await client.getLook(name);
  commit(analysis);
  return analysis;
}
