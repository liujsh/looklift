# v2.1 Acceptance Preview Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository rules prohibit subagent execution.

**Goal:** Restore responsive template/manual/AI previews, gate candidate decisions on the matching rendered frame, and make each AI refine click perform exactly one bounded round.

**Architecture:** Keep the Tauri drag/drop subscription stable for the lifetime of a Canvas/client and route events through the latest `loadPath` callback held in a ref. Treat every display-analysis mutation as a render invalidation, then let the Canvas mark only the completed request ready. Keep refinement count in the workflow so each explicit click advances one round and concurrent clicks are rejected.

**Tech Stack:** React 19, TypeScript, Vitest, happy-dom, Tauri 2, existing Python sidecar API.

## Global Constraints

- Register at most one native drag/drop listener per mounted Canvas/client.
- Preserve Tauri path drops, HTML5 file drops, file selection, preview debounce, and stale-response rejection.
- Never commit a candidate until its current preview has status `ready`.
- Keep a failed candidate available for discard/retry; the formal version must not change.
- One “AI 精修” click performs one provider call; at most two extra refinement rounds follow the initial request.
- Do not add backend API or database schema changes.

---

### Task 1: Stabilize Canvas drag/drop lifecycle

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Modify: `frontend/src/components/CanvasPane.tsx`
- Create: `frontend/src/components/CanvasPane.lifecycle.test.tsx`

**Interfaces:**
- Consumes: `listenForTauriDrops(element, { onActive, onPath }): Promise<UnlistenFn>` and `loadPreviewPair(...)`.
- Produces: a Canvas whose native listener is stable while its latest analysis/factor still schedules one final `/api/preview`.

- [ ] **Step 1: Add the DOM test runtime and write the failing lifecycle test**

Run `pnpm add -D happy-dom`, then create a test using `// @vitest-environment happy-dom`. Mock `listenForTauriDrops`, render `CanvasPane`, invoke the captured `onPath`, then rerender with several analysis/factor values. Assert the listener was called once, its unlisten function was not called during rerenders, and the final debounced `client.preview` payload contains the latest analysis/factor.

```tsx
expect(listenForTauriDrops).toHaveBeenCalledTimes(1);
expect(unlisten).not.toHaveBeenCalled();
expect(client.preview).toHaveBeenLastCalledWith(
  expect.objectContaining({ analysis: latest, factor: 0.7 }),
  expect.any(AbortSignal),
);
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pnpm vitest run src/components/CanvasPane.lifecycle.test.tsx`

Expected: FAIL because changing `analysis` rebuilds `loadPath`, which tears down and recreates the native listener.

- [ ] **Step 3: Route the stable listener through the latest load callback**

In `CanvasPane.tsx`, keep the callback current without making the listener effect depend on it:

```tsx
const loadPathRef = useRef<(path: string) => Promise<void>>(async () => undefined);
// after loadPath is declared
loadPathRef.current = loadPath;

useEffect(() => {
  const element = paneRef.current;
  if (!element || !client) return;
  let cancelled = false;
  let unlisten: (() => void) | undefined;
  void listenForTauriDrops(element, {
    onActive: setDragActive,
    onPath: (path) => { void loadPathRef.current(path); },
  }).then((stop) => {
    if (cancelled) stop();
    else unlisten = stop;
  }).catch(() => undefined);
  return () => { cancelled = true; unlisten?.(); };
}, [client]);
```

- [ ] **Step 4: Run lifecycle and existing Canvas tests and verify GREEN**

Run: `pnpm vitest run src/components/CanvasPane.lifecycle.test.tsx src/features/canvas`

Expected: all selected tests PASS; no repeated listener registration on prop rerender.

- [ ] **Step 5: Commit Task 1**

```powershell
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/components/CanvasPane.tsx frontend/src/components/CanvasPane.lifecycle.test.tsx
git commit -m "fix(canvas): 稳定拖图监听与实时预览"
```

### Task 2: Gate candidate decisions on render completion

**Files:**
- Modify: `frontend/src/store/editorStore.ts`
- Modify: `frontend/src/store/editorStore.test.ts`
- Modify: `frontend/src/components/ChatPane.tsx`
- Modify: `frontend/src/components/ChatPane.test.tsx`
- Modify: `frontend/src/app/EditorShell.tsx`
- Modify: `frontend/src/features/sessions/sessionCoordinator.test.ts`

**Interfaces:**
- Consumes: `EditorState.render`, `onRenderStateChange`, and `SessionCoordinator.requirePending` semantics.
- Produces: pending candidates retained through render errors, decision buttons gated by `render.status`, and immediate render invalidation after display changes.

- [ ] **Step 1: Write failing store and ChatPane tests**

Add assertions that `beginPendingPreview`, manual preview changes, library commits, and factor changes set render status to `rendering`; a later render error retains `pendingPreview`. Render `ChatPane` with `renderStatus="rendering"` and assert accept/manual/refine are disabled while discard stays enabled and “正在渲染候选预览” is visible.

```tsx
expect(store.getSnapshot().render.status).toBe("rendering");
store.setRenderState({ status: "error", error: "失败" });
expect(store.getSnapshot().pendingPreview).not.toBeNull();

expect(html).toContain("正在渲染候选预览");
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pnpm vitest run src/store/editorStore.test.ts src/components/ChatPane.test.tsx src/features/sessions/sessionCoordinator.test.ts`

Expected: FAIL because mutations retain stale `ready`, render errors clear pending, and ChatPane has no render-status gate.

- [ ] **Step 3: Implement render invalidation and decision gating**

In `editorStore.ts`, use a helper when an image is present:

```ts
const invalidatedRender = () => state.imagePath
  ? Object.freeze({ status: "rendering" as const, error: null })
  : state.render;
```

Apply it to display-changing mutations and remove the line that clears pending on render error. Add `renderStatus: RenderStatus` to `ChatPaneProps`; disable accept/manual/refine unless `renderStatus === "ready"`, leave discard controlled only by action/request busy state, and display the rendering/error hint. Pass `editor.render.status` from `EditorShell`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pnpm vitest run src/store/editorStore.test.ts src/components/ChatPane.test.tsx src/features/sessions/sessionCoordinator.test.ts`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add frontend/src/store/editorStore.ts frontend/src/store/editorStore.test.ts frontend/src/components/ChatPane.tsx frontend/src/components/ChatPane.test.tsx frontend/src/app/EditorShell.tsx frontend/src/features/sessions/sessionCoordinator.test.ts
git commit -m "fix(chat): 按候选渲染状态开放决策"
```

### Task 3: Make refinement one explicit round per click

**Files:**
- Modify: `frontend/src/features/chat/chatWorkflow.ts`
- Modify: `frontend/src/features/chat/chatWorkflow.test.ts`
- Modify: `frontend/src/components/ChatPane.tsx`
- Modify: `frontend/src/components/ChatPane.test.tsx`

**Interfaces:**
- Consumes: `ChatWorkflowState.round`, `runStep(message, round)`, and pending candidate analysis.
- Produces: `refine(): Promise<void>` with one provider call per invocation, a two-extra-round limit, and synchronous duplicate-call rejection.

- [ ] **Step 1: Replace the automatic-loop test with failing per-click tests**

Assert initial `send` uses refinement count 0, the first and second `refine()` calls each add exactly one provider call using the newest candidate, the third call makes no provider request and reports `round_limit`, and two concurrent calls cannot issue two requests.

```ts
await workflow.send("先调整");
await workflow.refine();
expect(chatStep).toHaveBeenCalledTimes(2);
await workflow.refine();
expect(chatStep).toHaveBeenCalledTimes(3);
await workflow.refine();
expect(chatStep).toHaveBeenCalledTimes(3);
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pnpm vitest run src/features/chat/chatWorkflow.test.ts src/components/ChatPane.test.tsx`

Expected: FAIL because one `refine()` currently loops over two rounds.

- [ ] **Step 3: Implement one-round refinement and the hard limit**

Change `send` to call `runStep(message, 0)`. In `refine`, reject while `phase === "requesting"`, stop without a provider call when `round >= 2`, otherwise call `runStep` once with `round + 1`. Preserve `done`, `no_changes`, cancellation, and pending candidate behavior. Update ChatPane progress copy to distinguish the initial request from `AI 精修第 N/2 轮`.

- [ ] **Step 4: Run focused and full frontend verification**

Run: `pnpm vitest run src/features/chat/chatWorkflow.test.ts src/components/ChatPane.test.tsx`

Expected: focused tests PASS.

Run: `pnpm vitest run; pnpm exec tsc --noEmit; pnpm build`

Expected: all frontend tests PASS, TypeScript passes, and Vite production build succeeds.

- [ ] **Step 5: Commit Task 3**

```powershell
git add frontend/src/features/chat/chatWorkflow.ts frontend/src/features/chat/chatWorkflow.test.ts frontend/src/components/ChatPane.tsx frontend/src/components/ChatPane.test.tsx
git commit -m "fix(chat): 单次触发一轮 AI 精修"
```

### Task 4: Release-side verification and acceptance handoff

**Files:**
- Modify: `docs/versions/v2.1/tasks.md`
- Modify: `docs/history/dev-log.md`

**Interfaces:**
- Consumes: completed frontend fixes and the existing sidecar staging workflow.
- Produces: an acceptance-ready v2.1 dev build and documented manual checks.

- [ ] **Step 1: Run repository regression checks**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: Python suite passes with only the existing optional skip.

Run: `.venv\Scripts\python.exe -m ruff check looklift tests`

Expected: PASS.

Run: `cargo check --manifest-path frontend/src-tauri/Cargo.toml`

Expected: PASS.

- [ ] **Step 2: Update acceptance notes without pre-checking human-only results**

Record the diagnosed request storm, automated verification, and these remaining manual checks: one Tauri event listener lifecycle, manual/template after changes, diff reveals distinct images, candidate buttons unlock only after render, and one refine click produces one round.

- [ ] **Step 3: Commit verification notes**

```powershell
git add docs/versions/v2.1/tasks.md docs/history/dev-log.md
git commit -m "docs(v2.1): 记录预览回归复验"
```

- [ ] **Step 4: Rebuild and stage the sidecar only if Python source changed**

No Python source is planned to change. Reuse the already rebuilt v2.1 sidecar; restart `pnpm tauri dev` so Vite serves the fixed frontend. If Python files differ unexpectedly, rebuild with the README PyInstaller command before staging.
