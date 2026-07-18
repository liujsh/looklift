# 旧迭代文档规范（归档）

> 本文保留 2026-07-16 起的旧规范与决策记录；当前存放规范以 [文档中心](../README.md) 为准。

> 2026-07-18 更新:产品升级为平台化 v2 一站式应用(见 [产品需求](../product/requirements.md))。
> v2.0-A 与 v2.0-B 作为 2.0.0 的内部开发阶段；完成 M1-M8 人工验收后共同收口发布。
> 后续顺序为 v2.1 AI Studio、v2.2 平台外壳、v2.3-A 本地图库、RAW 可行性门、v2.3-B 设备导入、
> v2.4 模板教学、v2.5 自动化、v2.6 受控插件。

## 结构约定

每个迭代一个文件夹 `docs/versions/<版本>/`,固定三份文档:

| 文档 | 内容 | 回答的问题 |
|---|---|---|
| `requirements.md` | 一句话目标、覆盖的用户故事(引 U 编号)、可勾选验收标准、非目标、对前置版本的依赖 | 做什么、做到什么程度、不做什么 |
| `design.md` | 关键设计决策(选项+推荐+理由)、架构/文件结构、接口与数据结构变化、风险 | 怎么做、为什么这么做 |
| `tasks.md` | 按依赖排序的可执行任务,每任务一句验收;**人工验收项集中放最后单独一区** | 按什么顺序做、怎么验 |

## 生命周期

1. **草拟**:迭代开工前撰写,文首标注「状态:草拟,待作者 review」
2. **评审**:作者 review 通过后改为「状态:已确认(日期)」,方可开工;
   开工时由 spec 生成同版本实施计划(`docs/versions/<版本>/plans/`,TDD 步骤级)
3. **实现**:开发期间 spec 是验收依据;需求变更先改 spec 再改代码
4. **归档**:版本发布后,把架构要点回填 [architecture.md](../product/architecture.md)(只记已实现的实况),
   spec 文件夹不再修改,作为历史记录保留

## 与其他文档的关系

- [产品需求](../product/requirements.md) 是产品宪法:定位、模块总览、用户故事总表、路线图。
  spec 只展开其中**一行**(一个版本),范围不得超出对应 roadmap 行
- [架构实况](../product/architecture.md) 只记录**已实现**的架构;未实现的设计留在各版本目录
- [旧任务快照](legacy-tasks.md) 只保留历史记录
- v0.3 早于本规范,是单文件 spec([v0.3/spec.md](../versions/v0.3/spec.md))
  加 [实施计划](../versions/v0.3/plans/implementation.md);文件夹规范自 v0.4 起执行

## 待作者决策(汇总,不阻塞草拟)

来自各版本 spec 撰写过程,按版本归类;定了之后写回对应 spec 并从这里划掉:

**v2 一站式(2026-07-18 敲定的锁定项,不再是待决)**:渲染=numpy+numba+pyvips;GUI=Tauri+React+
Python sidecar;先全局不做局部;平台外壳参考 Open Design、Studio 参考 Lightroom；图库映射本地文件夹；
对外品牌写作 **LookLift**，仓库、包、CLI 与配置键继续使用 `looklift`。
**仍待作者拍板(不阻塞)**:
- [ ] **商业化意图**:影响许可(现 MIT;方案全程许可干净不碰 GPL);若商业化需确认各宽松依赖逐个合规。
- [ ] **v0.4 收尾取舍**:终审 16 项——引擎/安全层必修(carry forward),纯 pywebview 前端小问题随 v2 React 重写自然消解,是否认可?
- [ ] **Tauri+Python sidecar 打包**:定为 v2.0-B 第一个 gated 任务(go/no-go,失败回退 pywebview),不预先假定成功。



- [x] **v0.4**:pywebview 依赖方式——~~已确认为 optional extra~~,已实现:
  `looklift[gui]`(`pyproject.toml` `[project.optional-dependencies]`),CLI-only
  用户不强制安装
- [x] **v0.4**:配置向导是否允许「稍后配置」跳过——~~已确认允许~~,已实现:向导有
  "稍后配置"按钮,只有触发"分析"才真正需要 provider,库面板/报告页浏览不受影响
- [x] **v0.4**:强度缩放语义确认——~~已按推荐实现~~:`color_grading` 的 `hue`/
  `blending` 不随强度缩放,其余按比例缩、曲线向恒等线插值(见
  [architecture.md](../product/architecture.md) §17)
- [x] **v0.4**:是否引入 Shoelace——~~已确认不需要~~:现有 `.form`/`.field`/原生
  `<input type="range">` 配方足够覆盖滑杆/向导/对比条,零新增前端依赖(见
  [v0.4/design.md](../versions/v0.4/design.md) 决策 5)
- [ ] **v0.4**:pywebview 版本钉(草案 `>=5,<6`)待实测确认(拖拽 API 可用性)——
  **仍待作者在真实 WebView2 环境验证**,不是自动化测试能覆盖的范围
- [ ] **v0.4**:分析面板"导出预设/sidecar"要求先成功收藏到风格库(`POST /api/looks`)
  才能导出——这是 [v0.4/design.md](../versions/v0.4/design.md)「API 路由一览」五条
  `/api/looks*` 路由表的忠实实现,但 requirements.md 原始措辞("分析面板能导出
  预设")读起来像是分析完就能直接导出、不必先收藏,存在歧义。当前实现选择
  "先收藏"(理由见 [dev-log.md](dev-log.md) 自主决策记录),**待作者确认这条
  UX 是否符合预期**——如需改为"未收藏也能临时导出",需要新增一条 design.md
  未定义的路由
> v0.6、v0.7 已于 2026-07-18 终止：前者拆入 v2.4，目录风格聚类取消；后者被 v2.0-B 的
> Tauri 打包方案取代。原三文档保留作历史记录，不得生成实施计划。
