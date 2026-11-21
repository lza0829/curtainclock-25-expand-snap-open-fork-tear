# Curtainclock（幕窗钟）

骨架：**周模板 → 展开多日草稿批窗（快照定格）→ 算力槽/执行器资源依赖就绪 → 开窗租约占用 → 关窗释放与冲突水位互证**

- 前端：http://127.0.0.1:6100 （React + Vite）
- API：http://127.0.0.1:11100

## 资源绑定口径：快照臂（全局唯一，不混跟随臂）

「已展开草稿听谁的资源绑定」——**以展开时刻快照为准**：

- 展开时把模板的算力槽/执行器/时段**抄进**各日批窗（`windows.slot_code/executor_code/day/start_min/end_min`），并记 `windows.template_version`；
- 之后改模板只 `templates.version + 1`、整组换条目，**绝不回写**已展开草稿，更不得静默改已 live 占用；
- 开窗预检（`/windows/{code}/ready`）与租约实资源（`leases` 各行）只读批窗自身快照列，不感知模板表 —— 改模板与开窗并发也不存在"半截重绑"；
- `template_version` 三处可查：模板列表、批窗列表（来源列 `模板·vN`）、展开审计（`/expansions`）；
- 展开幂等：同（模板， 周）已有存留批窗即复用原展开（`reused=true`），并发展开在 `BEGIN IMMEDIATE` 下串行，**不双份草稿**；该周批窗全作废后可按现行版本重展开，有已结束批窗的周封存；
- 想让旧草稿跟新模板：作废草稿再展开（仅 draft 可作废，live/done 一律 409）。

## 本地冒烟（推荐）

```powershell
cd D:\Asolo11\claude-workspace\curtainclock\source
# 本机若无 3.11：py -V:Astral/CPython3.11.15 -m venv .venv
py -V:Astral/CPython3.11.15 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:PYTHONPATH = "$PWD\backend"
Start-Process .\.venv\Scripts\uvicorn.exe -ArgumentList 'app.main:app','--host','127.0.0.1','--port','11100' -WorkingDirectory "$PWD\backend"
cd frontend
# 前端需 Node ≥18；不足时用 docker compose 起 web
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:6100 ：开一节课 → 同算力槽冲突 → 关窗释放。

## Docker

```powershell
docker compose up -d --build
```
