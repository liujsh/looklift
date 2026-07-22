import { convertFileSrc, isTauri } from "@tauri-apps/api/core";
import type { LibraryItem } from "../api/types";

type LibraryCardProps = {
  item: LibraryItem;
  onOpen(item: LibraryItem): Promise<void>;
  onReveal(item: LibraryItem): Promise<void>;
  onTags(item: LibraryItem): Promise<void>;
};

export function LibraryCard({ item, onOpen, onReveal, onTags }: LibraryCardProps) {
  const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "尺寸未知";
  const shooting = shootingInfo(item);
  return <article className="library-card" data-available={item.available}>
    <div className="library-thumbnail">
      {item.thumbnail_path && isTauri()
        ? <img src={convertFileSrc(item.thumbnail_path)} alt="" />
        : <span>{item.file_format || "图片"}</span>}
    </div>
    <div className="library-card-body">
      <strong title={item.path}>{item.display_name}</strong>
      <span>{item.available ? `${item.file_format} · ${dimensions} · ${formatBytes(item.file_size)}` : "原文件已缺失"}</span>
      {shooting && <span>{shooting}</span>}
      {item.current_version_id && <span>当前版本 · {item.current_summary || item.current_version_id}</span>}
      {item.export_count > 0 && <span>已导出 {item.export_count} 次</span>}
      <div className="library-tags">{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
    </div>
    <footer>
      <button type="button" disabled={!item.available} onClick={() => void onOpen(item)}>进入 Studio</button>
      <button type="button" aria-label="在资源管理器中显示" disabled={!item.available} onClick={() => void onReveal(item)}>定位文件</button>
      <button type="button" onClick={() => void onTags(item)}>编辑标签</button>
    </footer>
  </article>;
}

function shootingInfo(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.metadata.iso) parts.push(`ISO ${item.metadata.iso}`);
  if (item.metadata.aperture) parts.push(`f/${item.metadata.aperture}`);
  if (item.metadata.shutter_seconds) {
    const shutter = item.metadata.shutter_seconds < 1
      ? `1/${Math.round(1 / item.metadata.shutter_seconds)}s`
      : `${item.metadata.shutter_seconds}s`;
    parts.push(shutter);
  }
  if (item.metadata.focal_length_mm) parts.push(`${item.metadata.focal_length_mm}mm`);
  return parts.join(" · ");
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
