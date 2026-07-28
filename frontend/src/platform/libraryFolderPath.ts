import type { LibraryRoot } from "../api/types";

export type Crumb = { label: string; path: string | null };

const SEP = /[\\/]/;

export function folderCrumbs(folder: string | null, roots: LibraryRoot[]): Crumb[] {
  const home: Crumb = { label: "首页", path: null };
  if (folder === null) return [home];
  const root = roots.find((r) => folder === r.path || folder.startsWith(r.path + "\\") || folder.startsWith(r.path + "/"));
  if (!root) return [home];
  const sep = root.path.includes("\\") ? "\\" : "/";
  const rootSegments = root.path.split(SEP);
  const rootName = rootSegments[rootSegments.length - 1] || root.path;
  const crumbs: Crumb[] = [home, { label: rootName, path: root.path }];
  const rest = folder.slice(root.path.length).split(SEP).filter(Boolean);
  let acc = root.path;
  for (const segment of rest) {
    acc = acc + sep + segment;
    crumbs.push({ label: segment, path: acc });
  }
  return crumbs;
}
