# looklift Tauri 前端

v2.0-B 的 React + TypeScript + Vite 前端与 Tauri 2 桌面壳。Python 引擎以
PyInstaller onedir sidecar 形式随包分发。

## Windows 构建

1. 安装 Rustup 和 Visual Studio 2022 C++ Build Tools。
2. 在仓库根目录构建 `packaging/looklift-engine.spec`。
3. 运行 `pnpm install`。
4. 运行 `pnpm tauri build`；`beforeBuildCommand` 会把 onedir 产物暂存到
   gitignore 的 `src-tauri/binaries/`。

Windows 中文用户名下，`Launch-VsDevShell.ps1` 可能损坏 `USERPROFILE`/
`LOCALAPPDATA` 编码。若在自动化脚本中调用它，应先保存这些环境变量，
调用后恢复，再执行 cargo/pnpm。
