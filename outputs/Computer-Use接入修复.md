# Computer Use 接入修复

2026-09-27：本次日志明确记录 node_repl / cua_repl 启动失败：目录名称无效 (os error 267)。对话工作目录 E:\tft_helper 不存在，而实际项目位于 E:\tft-helper。工具服务未单独配置 cwd，继承会话目录。独立启动普通子进程复现 WinError 267。

已建立目录联接 E:\tft_helper → E:\tft-helper，未搬移或复制项目，未修改插件、权限或全局配置。验证旧路径可以启动进程，且两个路径下 app.py 为同一文件。普通子进程启动错误已消除。

当前已启动会话的 MCP 客户端仍返回先前启动失败，尚未确认 node_repl 工具成功发布；需要会话重新初始化工具后检查。未操作 MuMu 或开始游戏。

证据：work/companion/computer-use-path-repair.json；桌面日志 C:\Users\Robin\AppData\Local\Codex\Logs\2026\09\27\codex-desktop-c1c268db-62ab-4e8a-a0d9-4abc9b831bf1-19112-t0-i1-034505-0.log（03:46:07 UTC）。

## 工具恢复后的截图诊断

工具已可调用，服务日志显示 node_repl ready。MuMu 游戏与启动器均可枚举，但截图返回 FrameArrived/window capture timed out。额外打开空白记事本作为对照，同样截图超时；MuMu 和记事本的可访问性文字均能读取。重置 node_repl 并重新导入 sky 后，MuMu 截图仍超时。因此故障不局限于游戏窗口，具体图形采集根因尚未确认。没有更改显卡、系统权限或游戏设置，没有进入匹配。
