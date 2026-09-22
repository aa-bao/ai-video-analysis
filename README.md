# xxzw-video · AI 视频解析 Agent（P2）

从 `xxzw-rag` 单体中切分出的独立项目（阶段 5a）。完整视频解析流水线：
提交视频 URL 或本地文件 → 异步下载 / 字幕 / 音频 → 语音转写（火山引擎录音文件极速识别）
/ 抽帧 → 摘要（豆包方舟 Chat）→ 返回转录、关键帧、摘要、HTML 报告等结构化结果。

## 目录

```
src/
├── api/        # app.py（组合根）+ router_auth / router_users + video 路由在 src/video/router.py
├── auth/       # 本地账号：口令哈希 / 登录会话 / 限流
├── core/       # config（APP_ENV / 数据根 / 密钥根）· identity · security
├── db/         # base / session / models（4 表）/ repositories（2 仓储）/ scope
├── models/     # client（中转 HTTP + 错误分类）· llm（ChatClient）
├── shared/     # errors · config（P2 精简版）
└── video/      # 视频域本体：acquire / asr / audio / frames / summary / report /
                # transcript / cookies / settings / config / service / router
```

> `src/video/` 保留了原包名（方案 §6.1 画的是 `<domain>/` 直挂 `src/`）——
> 保持包名使域内 30+ 处 `from src.video.X import ...` 零改写，显著降低切分风险。

## 本地运行

```bash
# 1) 环境
python -m venv .venv && .venv/Scripts/activate      # Windows
uv sync                                             # 或 pip install -e .

# 2) 建库（P2 独立 database）
psql "$DATABASE_URL" -f schema.sql

# 3) 起服务
uvicorn src.api.app:create_app --factory --port 8010
```

健康探针：`/api/health/live`（恒 200）、`/api/health/ready`（DB 可达，失败 503）。

## 测试

```bash
python -m pytest -q -p no:cacheprovider
```

`tests/test_video/` 为纯单元测试，**不需要 Docker / 数据库**。

## 部署（阶段 5b）

P2 与 P1 共用**同一个 PG 容器**（方案 §7.1：1 个容器、2 个 database `rag` / `video`）。
P2 自身**不带 postgres**，连的是 P1 起的那个 PG 实例里的 `video` 库；两端同处
`xxzw-net` 网络，P1 的 PG 服务名为 `postgres`、容器名 `xxzw-postgres`。

> ⚠️ **启动前提：先起 P1 的 PG，再起 P2。** 跨 compose 文件的 `depends_on` 不生效，
> 若 P2（含 `db-migrate`）在 PG 就绪前启动，会连不上 `postgres` 而失败；PG 就绪后
> 重跑即可（`db-migrate` 幂等，可重复执行）。此外，P1 侧也须把默认网络命名为
> `xxzw-net`（与 P2 一致），否则两 compose 各用各自 auto 网络、容器名无法互访。

```bash
# 0) 准备环境变量
cp .env.example .env          # 填写 POSTGRES_USER/PASSWORD（须与 P1 的 .env 一致）、
                              # 各 VOLC_* / MODEL_RELAY_* 密钥、VIDEO_* 阈值

# 1) 先起 P1（含 PG + rag 库结构）。P1 侧命令示例：
docker compose -f ../xxzw-rag/docker-compose.yml up -d

# 2) 起 P2（视频解析是 2C4G 上唯一重负载，默认不启，按需 --profile video）
docker compose --profile video up -d
```

### 端口表

| 服务          | 容器内        | 宿主映射            | 说明                              |
|---------------|---------------|---------------------|-----------------------------------|
| `video`（后端）| 8010          | `127.0.0.1:8010`    | FastAPI；探针 `/api/health/live`  |
| `web`（前端）  | 80            | `127.0.0.1:8080`    | nginx，反代 `/api/` → `video:8010`|
| `wx-channels`  | 2022          | `127.0.0.1:2022`    | 微信视频号下载（仅 P2 拥有）       |

> P1 的 web 已占宿主 `8000`，故 P2 前端改用 `8080`。PG 的 `5432` 由 P1 暴露，P2 不经宿主直连。

### 前端形态（重构口径，改页面前先读）

导航壳：**无左侧栏**，只有顶部 sticky 玻璃导航（品牌 / 纯文字导航 + 2px 指示条 / 账号下拉）+ 全站页脚。
首页是**落地页式长页**（形态参考 <https://github.com/liyupi/free-video-downloader>）：

| 区块 | 组件 | 说明 |
| --- | --- | --- |
| Hero | `views/VideoAnalysisView.vue` | 状态胶囊 → 大标题（主色尾缀）→ **胶囊搜索条**（内嵌主按钮）→ 选项行 → 识别平台胶囊行。选中任务后收窄为 `hero--compact` |
| 能力 3×2 | `components/FeatureGrid.vue` | 6 张卡片 |
| 三步流程 | `components/HowToSteps.vue` | 序号磁贴 + 连接箭头 |
| 产物清单 | `components/OutputList.vue` | 单块玻璃面板双列 |
| 页脚 | `components/AppFooter.vue` | 由 `AppLayout` 在 `RouterView` 之后渲染 |
| 区段头 | `components/SectionHead.vue` | 居中标题（可带主色尾缀）+ 一行说明 |
| 任务列表 | `components/TaskList.vue` | `layout="grid"` = 首页「最近的解析」区段；`layout="rail"` = 工作区左侧常驻任务栏 |

**任务列表的两处落位（2026-09-22 换位置）**：原为 Hero 右上角按钮弹出的**右侧抽屉**（会盖住内容），
抽屉已整体删除，改为

1. **首页** Hero 正下方的「最近的解析」内联区段（`tasks` 为空时不渲染）；
2. **选中任务后** 工作区**左侧 208px 常驻任务栏**，可边跑边切，不必退出当前任务。

状态文案（完成 / 解析中 / 排队中 / 文件 vs 链接 / 时刻）走 `src/utils/task-display.ts`，
与「AI 执行过程」卡片里的状态标签**同源**，改一处即可，别再各写一份。

三条不能顺手改回的实现口径：

1. **滚动归 `.app-main`**（`AppLayout`），全部页面取消了各自的 `overflow-y`，页脚才能随内容走；
   `.app-frame :deep(.page) { flex: 1 0 auto }` 负责「短页撑满 / 长页把页脚顶下去」。
   ⚠️ 路由切换因此**不再天然回顶**，靠 `watch(route.fullPath)` 显式 `scrollTo({ top: 0 })`。
2. **滚动条全局隐藏**：`style.css` 的 `* { scrollbar-width: none }` + `*::-webkit-scrollbar { display: none }`。
   **只是外观**，滚轮 / 触控板 / 键盘 / 触屏 / 拖拽轨道区都可滚。要恢复：删掉该段，或给容器加 `.show-scrollbar`。
   ⚠️ **组件级的 `scrollbar-width: thin` 会以更高优先级把滚动条露回来** —— 加任何自定义滚动条样式前先在
   `src` 里 `grep scrollbar` 确认没有漏网的（本仓已清空）。
3. **版心 70%**，顶栏内层 / 页面内容 / 页脚内层三点同轴；窄屏 86%（≤1180px）/ 100%（≤900px）。
4. **工作台是两栏 + 第 3 面板通栏**：任务栏占掉 208px 后，1600 视口下工作台只剩 ~890px，
   原三栏最小宽 1020px 会**横向溢出** → 收成两栏（`执行过程 | 解析结果`），
   **媒体页 / 图文问答通栏落在第 2 行**（`grid-column: 1 / -1`；挤在 494px 里放播放器与问答都太窄）。
   断点：≤1360px 任务栏转整宽横排、≤1100px 工作台单列。
5. **访客配额提示只有一处**：Hero 状态胶囊 `免登录体验 · 单条上限 20 分钟 · 剩余 4/5 次`
   （`src/api/quota.ts::guestQuotaHint` 是唯一来源）。计数是 `rag_visitor.upload_count`，
   **累计值、没有每日重置**，所以文案里不写「今日」。

视觉基线 = `../xxzw-rag/docs/前端页面设计规范.md`（Apple 玻璃拟态 / 令牌唯一 / 弹簧物理），
设计上下文见本仓 `.impeccable.md`（**规约优先于 impeccable 的审美主张**）。

### 前端静态资源缓存（排查白屏必读）

`web/nginx/default.conf.template` 有三条**不得回退**的规则：

- `location = /index.html` → `Cache-Control: no-cache, no-store, must-revalidate`。
  镜像构建用 `touch -d @SOURCE_DATE_EPOCH(0)` 归一 mtime（为可复现），响应带
  `Last-Modified: 1970-01-01`，浏览器会按启发式（≈5.6 年）把入口 HTML 当长期新鲜、**从不回源**，
  于是**重新部署后老用户必然白屏**。
- `location /assets/` → `try_files $uri =404` + `immutable`。**缺失资源必须 404**；
  若落进 SPA 回退会以 `text/html` 返回，被 strict MIME 检查拒绝，真实原因（资源不存在）被伪装成
  `Refused to apply style … MIME type ('text/html')` / `Failed to load module script … text/html` 的整页白屏。
- 嵌套路由归一化用 `rewrite … last`（非 `break`），使归一化后仍能得到 404 而不是又一次回退。

> 遇到上述 MIME 报错：**先硬刷新（Ctrl+Shift+R）**；仍不行再
> `curl -sI http://localhost:8080/assets/<报错哈希>.js` 看真实状态码。

### 视频库的隔离口径

⚠️ **库是「按 owner 隔离」的，不是全站共享、也不是按角色分。**
`GET /api/video/library` 走 `VideoTaskRepository.list_owned()`，条件是
**`owner_user_id == identity.user_id`**（外加 `scope_condition()`，当前恒真）。

由此推出三条实务结论：

1. **访客 / 账号各看各的**。访客是影子账号，但**每个访客一个影子 user_id**，
   所以两个访客互相看不到对方的库（实测：`owner_user_id=25` 与 `30` 各只看到自己那两条）。
2. **同一账号换设备 / 清 Cookie 后仍能看到自己的历史**（绑 `user_id`，不绑浏览器）。
3. **访客换新身份后看到空库** —— 这是预期，不是数据丢了；原数据仍在库里，
   只是归属另一个 owner。

删除同理：`DELETE /api/video/library/{task_dir}` 要求 owner 匹配，
越权返回 404（不是 403，避免泄露「该任务存在」）。

> 若将来要「公共库」（所有人可见），改 `scope_condition()` 一处即可 ——
> 那正是它被保留下来的原因（见 `src/db/scope.py` docstring）。

### 抖音 Cookie 过期怎么更新

抖音登录态失效后（表现为解析任务报 `captions_not_found` 后又下载失败、或 yt-dlp 报需登录），
按下面顺序处理。**路径 A 是一键，路径 B 是兜底。**

**路径 A — 设置页「从本机浏览器一键更新」（推荐）**

进入「设置 → 抖音 Cookie」，点 **从本机浏览器一键更新**。后端会：
1. 找到本机 Chrome / Edge / Brave 的 Cookie 库（多 profile 全扫）；
2. **只读复制**（连 `-wal`/`-shm` 一起带，否则读到旧快照）到临时目录；
3. 过滤 `douyin.com` / `iesdouyin.com` 域名，解密后转 Netscape 格式，**直接写入**共享文件。

对应接口：`POST /api/video/cookies/douyin/extract`（需 `settings_manage` 权限）。
`{"dry_run": true}` 可只导出不写入。

⚠️ **已知限制：Chrome 127+ 的 `v20`（App-Bound Encryption）解不开。**
Chrome 127 起 Cookie 用 `v20` 前缀，密钥在 `Local State` 的
`app_bound_encrypted_key`（`APPB` 前缀），由 Chrome 自己的 elevation service 保护 ——
**纯本地 DPAPI 复现不出来**（实测确认）。此时接口返回 400 并明确提示改用路径 B，
**这不是「你登录失效了」**。Chrome 里 `v10`/`v11` 的老 Cookie 或 Edge 的旧格式仍可自动解。

**路径 B — 手动粘贴 Netscape 格式（万能兜底）**

1. 浏览器登录抖音后，用扩展（如 *Get cookies.txt LOCALLY*）导出 **Netscape 格式**；
   或按 F12 → Network → 任一带 Cookie 的请求 → 复制 Cookie 头，再转成 tab 分隔的 7 列。
2. 粘进设置页的文本框 → **保存抖音 Cookie**（`PUT /api/video/cookies/douyin`）。
3. 校验规则（`src/video/cookies.py::parse_netscape_cookie`）：
   非注释行**至少 7 个 tab 字段**，且**至少一条是 douyin.com / iesdouyin.com 域名**，
   否则返回 400 `VIDEO_COOKIE_INVALID`。

**文件落点**：开发环境为仓库根 `cookies_douyin.txt`
（可用 `QUICK_WATCH_DOUYIN_COOKIE_FILE` 覆盖）；生产写入数据卷 `data/video/cookies/`。
每次保存会先**备份**旧文件。

⚠️ **别用 `yt-dlp --cookies cookies_douyin.txt` 手工测试 —— 它会原地重写这个文件。**
实测：62 条 / 9520B → 58 条 / 8667B，`#HttpOnly_` 前缀被剥掉、首行被换成
`# This file is generated by yt-dlp. Do not edit.`。**静默丢 4 条 cookie**，而且**每次解析都发生一次**。

代码侧已修（`acquire.py::ytdlp_cookie_args`）：交给 yt-dlp 的永远是 work_dir 下的**临时副本**，
生产文件只读。若你手工跑过 yt-dlp 导致 cookie 变少，用设置页重新保存即可恢复
（`save_douyin_cookie()` 会从导出文件重写为规范格式）。回归测试见
`tests/test_video/test_ytdlp_cookie_isolation.py`。

⚠️ **凭据不进镜像**：`.dockerignore` 已排除 `cookies.txt` / `cookies_douyin.txt` / `secrets`。
compose 用 `./data/video/cookies` 绑到容器内 `/app/data/video/cookies`，
所以**宿主侧更新 cookie 对容器即时生效、无需重建镜像**。



- **1 个 PG 容器**（P1 起），含两个独立 database：`rag`（P1）、`video`（P2）。
  同名表（如 `rag_user`/`rag_session`）因分库不冲突。
- `db-migrate` 在服务启动前把 `schema.sql` 灌入 `video` 库（表已 `IF NOT EXISTS`，幂等）；
  `video` 库若不存在会先建（幂等）。
- ⚠️ **`video` 库由 `db-migrate` 幂等创建，正常无需手工干预。** PostgreSQL 官方镜像**仅在数据卷为空时**
  才执行 `/docker-entrypoint-initdb.d/*.sql`（P1 的 `deploy/postgres/initdb/01-create-video-db.sql`
  即依赖该机制）—— **已有数据卷时它不会执行**，故不能依赖它建 `video` 库；`db-migrate` 里那句幂等的
  `CREATE DATABASE video` 才是可靠通路。万一需要手工兜底：

  ```bash
  docker compose exec postgres psql -U rag -c "CREATE DATABASE video;"
  ```
- P2 容器内数据根 `/app/data` 挂具名卷 `videodata`；35 GiB 硬配额由应用层实现
  （另一 agent 负责），运维需留意外部卷增长。
- `wx-channels` 的 `/data`（配置/下载/sqlite）与 `/cookies`（登录态）分别挂 `wxdata` / `wxcookies`。

### 资源（2C4G 轻量服务器）

- `video` 1 CPU / **2048 MiB**（常驻 ~300–500 MiB，ffmpeg 抽帧转码峰值另加 300–800 MiB；
  取 2048 而非 §7.2 的 1024 以覆盖 4K 转码不 OOM）；`web` 0.5 CPU / 256 MiB；
  `wx-channels` 1 CPU / 512 MiB。
- 全部组件 limit 之和约 4.68 GiB，超过物理 4 GiB；靠「P2 按需启动 + 视频任务全局串行 1
  （§7.3 容量前提）+ cgroup 按负载分配」吸收，极端全满载会触发 swap。
