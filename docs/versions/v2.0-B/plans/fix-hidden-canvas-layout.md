# 修复聊天关闭时画布消失 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 本仓库禁止派子代理，固定为当前会话内联执行。

**Goal:** 聊天栏关闭或窄屏隐藏时，照片画布仍固定占据主编辑列，并显示拖图与选择照片入口。

**Architecture:** 保持 `EditorShell` 的 DOM 顺序与现有尺寸不变，仅给工作台声明命名 Grid 区域。桌面布局固定为 `chat / canvas / controls`，窄屏布局固定为 `canvas / controls`；隐藏聊天栏不再影响其余面板的自动排布。

**Tech Stack:** React 19、TypeScript、CSS Grid、Vitest、Tauri 2。

## Global Constraints

- 不改变三栏视觉尺寸、颜色、交互文案或拖拽数据流。
- 不启用 v2.1 聊天功能。
- 先观察回归测试按预期失败，再修改生产 CSS。
- 不执行 Git add/commit/push；构建产物验证后由作者继续 M1–M8。

---

### Task 1: 固定工作台 Grid 区域

**Files:**
- Modify: `frontend/src/app/EditorShell.test.tsx`
- Modify: `frontend/src/theme/layout.css`

**Interfaces:**
- Consumes: `ChatPane` 的 `hidden` 状态，以及 `data-pane="canvas"`、`data-pane="controls"` 的稳定 DOM 语义。
- Produces: 桌面 `chat canvas controls` 与窄屏 `canvas controls` 的显式布局契约。

- [x] **Step 1: 写失败回归测试**

在 `EditorShell.test.tsx` 读取 `layout.css`，断言工作台声明命名区域，且 `.chat-pane`、`.canvas-pane`、`.panel-pane` 分别绑定区域；820px 断点改成两区域布局。

- [x] **Step 2: 运行测试并确认红灯原因**

Run: `pnpm vitest run src/app/EditorShell.test.tsx`

Expected: FAIL，提示缺少 `grid-template-areas` 或 `grid-area`，证明测试能捕获当前零宽画布问题。

- [x] **Step 3: 写最小 CSS 修复**

桌面工作台加入：

```css
grid-template-areas: "chat canvas controls";
```

并将三个 pane 绑定到对应区域。820px 断点加入：

```css
grid-template-areas: "canvas controls";
```

- [x] **Step 4: 运行定向测试和前端全量测试**

Run: `pnpm vitest run src/app/EditorShell.test.tsx`

Expected: PASS。

Run: `pnpm vitest run`

Expected: 全部 PASS。

- [x] **Step 5: 开发态验证**

Run: `pnpm build`

Expected: TypeScript 与 Vite production build 成功。

Run: `pnpm tauri dev`

Expected: 聊天关闭时画布位于中间主区域，显示“把照片拖到这里”和“选择照片”；真实文件拖入后产生预览。

- [x] **Step 6: 重建发布安装包**

从仓库根目录重新冻结 sidecar，随后在 `frontend` 执行 `pnpm tauri build`，再运行 `packaging/smoke_release.py`。

Expected: NSIS 安装包生成，发布冒烟显示真实渲染、三个内置模板、导出与 sidecar 回收通过。
