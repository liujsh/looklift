# v2.3-B 设备导入设计

设备源抽象为 `{id,name,path,kind}`。真实 Windows 环境通过可读盘符枚举；测试和无盘环境可用 `LOOKLIFT_IMPORT_SOURCES`（分号分隔路径）注入。浏览时递归读取图库支持扩展名，返回文件名、路径、大小、修改时间、格式、SHA-256 和是否已导入。

导入状态由 `device_import` 模块持有，任务状态为 `running/done/cancelled/error`。任务 worker 对每个文件执行同目录 `.looklift-import-<uuid>.tmp` 写入、`fsync`、尺寸和哈希校验、`os.replace`；目标路径冲突时追加短指纹。完成后调用 `LibraryStore.add_root`（必要时）和 `library_tasks.submit` 刷新索引。

HTTP 路由：`GET /api/import/sources`、`GET /api/import/items?source_id=&date=&unimported=`、`POST /api/import/start`、`GET /api/import/tasks/<id>`、`POST /api/import/tasks/<id>/cancel`。所有响应为中文错误信息，沿用 sidecar token 鉴权。
