# v2.1 T10 当前效果 AI 上下文与直方图实施计划

> 状态：自动实现与验证完成，待作者人工验收（2026-07-18）。
> 上游：[需求](../requirements.md) · [设计](../design.md) · [任务](../tasks.md)。
> 执行约束：当前工作区单代理顺序实施；迭代中仅跑受影响测试和类型检查，收口时全量验证一次。

## 目标

让 AI 接收与当前参数、强度同源的效果图；请求期间锁定会改变编辑状态的入口；在右侧显示由当前成功
预览计算的 RGB 直方图和安全拍摄信息。编辑参数仍表示中性调整量，不把 EXIF 或 JPEG 相机处理伪装成
滑杆初始值。

## T10.1 复用正式渲染管线生成 AI 当前效果图

涉及：`looklift/gui/api.py`、`looklift/ai_proxy.py`、`looklift/chat.py`、相关 Python 测试。

- 抽出可由预览 API 与 AI 代理共同调用的渲染入口，输入为图片路径、完整 analysis、factor 和输出边长。
- `prepare_ai_proxy` 先读取原片安全元数据，再按当前 analysis 与 factor 渲染最长边 2048px 的 RGB JPEG；
  临时文件不携带 EXIF/ICC，不进入图库、版本或导出目录，退出上下文后删除。
- Chat 请求增加必填 factor；参数文本与代理图使用进入请求时的同一快照。
- 保持原有错误映射：代理生成失败时不调用 provider，返回可恢复错误。
- 聚焦验证：
  `.venv\Scripts\python.exe -m pytest tests/test_ai_proxy.py tests/test_chat.py tests/test_gui_chat_api.py tests/test_gui_preview_api.py -q`。

## T10.2 提供安全拍摄信息

涉及：`looklift/ai_proxy.py`、`looklift/gui/api.py`、`frontend/src/api/types.ts`、
`frontend/src/api/client.ts` 及对应测试。

- 复用安全元数据白名单，增加只读图片信息 API；仅返回 ISO、快门、光圈、焦距、曝光补偿、白平衡、
  色彩空间和文件格式，不返回路径、文件名、时间、GPS、序列号或 MakerNotes。
- 前端在照片切换时读取，失败时静默降级为“拍摄信息不可用”，不影响编辑与 AI。
- 聚焦验证：相关 Python API 测试；前端运行
  `pnpm exec vitest run src/api/client.test.ts` 与 `pnpm exec tsc --noEmit`。

## T10.3 从成功预览异步计算直方图

涉及：`frontend/src/features/histogram/`（新增）、`frontend/src/components/CanvasPane.tsx`、
`frontend/src/components/HistogramPanel.tsx`（新增）及聚焦测试。

- Canvas 在 after 预览成功后向上报告 blob 与预览签名，不改变 `/api/preview` 的二进制响应契约。
- Web Worker 将效果图最长边缩至约 512px，统计 256 档 R/G/B 和两端裁切比例；纯计算函数与 Worker
  调度分离，便于无浏览器图像解码的单元测试。
- 调度器只接纳与当前预览签名一致的结果；新计算期间保留旧数据并显示“更新中”，失败只让直方图面板
  进入占位状态。
- 面板绘制叠加 RGB 曲线、阴影/高光裁切提示和简洁拍摄信息；滑杆仍保持中性调整量语义。
- 聚焦验证：
  `pnpm exec vitest run src/features/histogram/histogramModel.test.ts src/features/histogram/histogramController.test.ts src/components/CanvasPane.lifecycle.test.tsx src/components/HistogramPanel.test.tsx`
  与 `pnpm exec tsc --noEmit`。

## T10.4 冻结 AI 请求快照并锁定编辑

涉及：`frontend/src/store/editorStore.ts`、`frontend/src/features/chat/chatWorkflow.ts`、
`frontend/src/components/PanelPane.tsx`、`frontend/src/components/GalleryPane.tsx`、
`frontend/src/app/EditorShell.tsx` 及对应测试。

- Store 增加活动 AI 请求锁，锁持有者以单调 request ID 标识；锁定时拒绝参数、模板、强度、重置、
  撤销/重做等改变编辑状态的操作，切图会清锁并使旧请求失效。
- Chat 在读取 imagePath、displayAnalysis、factor 后立即加锁并提交快照；成功、失败、停止都按同一请求 ID
  解锁。响应仅在 request ID 仍活动且照片身份未变化时生成候选，否则直接丢弃。
- 右侧面板与模板入口反映锁定态；画布浏览、原图对比和停止请求保持可用。
- 聚焦验证：
  `pnpm exec vitest run src/store/editorStore.test.ts src/features/chat/chatWorkflow.test.ts src/components/PanelPane.test.tsx src/components/GalleryPane.test.tsx src/app/EditorShell.test.tsx`
  与 `pnpm exec tsc --noEmit`。

## T10.5 收口与人工验收

- 更新 `tasks.md`、架构说明和开发日志，记录当前效果代理、直方图派生数据与锁定边界。
- 人工验收：导入照片后滑杆为中性；拍摄信息与直方图出现；手动拉到明显过曝后请求 AI，确认捕获的
  参数和代理图均反映过曝；请求期间编辑入口不可用、停止后恢复；快速调参时直方图不会回跳。
- 最终全量验证仅运行一次：
  - `.venv\Scripts\python.exe -m pytest -q`
  - `cd frontend` 后运行 `pnpm test && pnpm build`

## 完成条件

- 当前效果图、current_analysis 与 factor 同源，原始画面不再冒充当前编辑效果发送给 AI。
- 所有编辑入口遵守请求锁；停止、切图和晚到响应不会覆盖新状态。
- 直方图只跟随成功预览且具备签名防过期与失败降级。
- 安全元数据边界、现有手调/预览/导出行为及 v2.1 候选确认流程无回归。

## T10.6 人工验收反馈修正

- 直方图改为深色高对比图底、加粗 RGB 曲线，并 sticky 在右侧滚动容器顶部；使用运行中的 `pnpm tauri dev`
  实际滚动检查，不为纯视觉变化增加测试。
- 在 `tests/test_chat.py` 先钉住系统提示词规则：当前渲染画面优先、仅显式要求才保护手调参数、支持的调整不得
  推给用户手调、不得仅凭参数绝对值判断问题；再修改 `looklift/chat.py`。
- 聚焦验证：`.venv\Scripts\python.exe -m pytest tests/test_chat.py -q` 和 Ruff；前端只运行
  `pnpm exec tsc --noEmit`，不重复执行全量测试或 production build。
