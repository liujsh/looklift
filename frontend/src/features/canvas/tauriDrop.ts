import { getCurrentWebview } from "@tauri-apps/api/webview";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { firstSupportedImage } from "./canvasModel";

type DropCallbacks = {
  onActive(active: boolean): void;
  onPath(path: string): void;
};

function isInside(element: HTMLElement, x: number, y: number): boolean {
  const scale = window.devicePixelRatio || 1;
  const rect = element.getBoundingClientRect();
  const logicalX = x / scale;
  const logicalY = y / scale;
  return logicalX >= rect.left && logicalX <= rect.right
    && logicalY >= rect.top && logicalY <= rect.bottom;
}

export async function listenForTauriDrops(
  element: HTMLElement,
  callbacks: DropCallbacks,
): Promise<UnlistenFn> {
  return getCurrentWebview().onDragDropEvent(({ payload }) => {
    if (payload.type === "leave") {
      callbacks.onActive(false);
      return;
    }
    const inside = isInside(element, payload.position.x, payload.position.y);
    callbacks.onActive(inside);
    if (payload.type === "drop" && inside) {
      const path = firstSupportedImage(payload.paths);
      if (path) callbacks.onPath(path);
      callbacks.onActive(false);
    }
  });
}
