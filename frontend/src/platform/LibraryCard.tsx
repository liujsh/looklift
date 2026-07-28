import { useEffect, useState } from "react";
import type { LibraryItem } from "../api/types";
import { Icon } from "./icons";

type LibraryCardProps = {
  item: LibraryItem;
  loadThumbnail(item: LibraryItem, signal: AbortSignal): Promise<Blob>;
  onOpen(item: LibraryItem): Promise<void>;
  onReveal(item: LibraryItem): Promise<void>;
  onTags(item: LibraryItem): Promise<void>;
};

export function LibraryCard({ item, loadThumbnail, onOpen, onReveal, onTags }: LibraryCardProps) {
  const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "尺寸未知";
  const shooting = shootingInfo(item);
  const thumbnailUrl = useThumbnail(item, loadThumbnail);
  return <article className="library-card" data-available={item.available}>
    <div className="library-thumb-wrap">
      <span className="sprocket tl" aria-hidden="true" />
      <span className="sprocket tr" aria-hidden="true" />
      <div className="library-thumb">
        {thumbnailUrl
          ? <img src={thumbnailUrl} alt="" />
          : <span className="library-thumb-fallback" aria-hidden="true">{item.file_format || "图片"}</span>}
      </div>
    </div>
    <div className="library-card-body">
      <strong title={item.path}>{item.display_name}</strong>
      {item.available
        ? <span className="library-card-line">{item.file_format} · {dimensions} · {formatBytes(item.file_size)}</span>
        : <span className="pill missing">源文件不可用</span>}
      {shooting && <span className="library-card-line">{shooting}</span>}
      {item.current_version_id && <span className="library-card-line">当前版本 · {item.current_summary || "已建立 Studio 会话"}</span>}
      {item.export_count > 0 && <span className="library-card-line">已导出 {item.export_count} 次</span>}
      {item.tags.length > 0 && <div className="library-tags">{item.tags.map((tag) => <span key={tag} className="pill tag">{tag}</span>)}</div>}
    </div>
    <footer className="library-actions">
      <button type="button" className="icon-btn primary" data-tip="进入 Studio" aria-label="进入 Studio" disabled={!item.available} onClick={() => void onOpen(item)}>
        <Icon name="aperture" />
      </button>
      <button type="button" className="icon-btn" data-tip="定位文件" aria-label="定位文件" disabled={!item.available} onClick={() => void onReveal(item)}>
        <Icon name="reveal" />
      </button>
      <button type="button" className="icon-btn" data-tip="编辑标签" aria-label="编辑标签" onClick={() => void onTags(item)}>
        <Icon name="tag" />
      </button>
    </footer>
  </article>;
}

function useThumbnail(
  item: LibraryItem,
  loadThumbnail: LibraryCardProps["loadThumbnail"],
): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    if (!item.thumbnail_path) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    void loadThumbnail(item, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.id, item.thumbnail_path, loadThumbnail]);
  return url;
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
