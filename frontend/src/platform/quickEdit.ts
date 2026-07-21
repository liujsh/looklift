import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import type { Analysis, CreateSessionRequest, SessionSnapshot } from "../api/types";

const IMAGE_ACCEPT = "image/jpeg,image/png,image/webp,image/tiff";
const IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "tif", "tiff"];

export type QuickEditDependencies = {
  initialAnalysis: Analysis;
  chooseNativePath?(): Promise<string | null>;
  chooseBrowserFile(): Promise<File | null>;
  upload(file: File): Promise<{ path: string }>;
  createSession(payload: CreateSessionRequest): Promise<SessionSnapshot>;
  openSession(snapshot: SessionSnapshot): void;
};

export type QuickEditResult = "opened" | "cancelled";

export async function chooseNativeImagePath(): Promise<string | null> {
  return open({
    title: "选择一张照片",
    multiple: false,
    directory: false,
    filters: [{ name: "照片", extensions: IMAGE_EXTENSIONS }],
  });
}

export function nativeImageChooser(): (() => Promise<string | null>) | undefined {
  return isTauri() ? chooseNativeImagePath : undefined;
}

export function chooseBrowserImageFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = IMAGE_ACCEPT;
    input.addEventListener("change", () => resolve(input.files?.[0] ?? null), { once: true });
    input.addEventListener("cancel", () => resolve(null), { once: true });
    input.click();
  });
}

export async function runQuickEdit(dependencies: QuickEditDependencies): Promise<QuickEditResult> {
  let path: string;
  if (dependencies.chooseNativePath) {
    const selected = await dependencies.chooseNativePath();
    if (!selected) return "cancelled";
    path = selected;
  } else {
    const file = await dependencies.chooseBrowserFile();
    if (!file) return "cancelled";
    path = (await dependencies.upload(file)).path;
  }

  const snapshot = await dependencies.createSession({
    path,
    initial_analysis: dependencies.initialAnalysis,
  });
  dependencies.openSession(snapshot);
  return "opened";
}
