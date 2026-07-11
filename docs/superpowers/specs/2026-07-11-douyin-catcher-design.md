# 抖音抓取器（Douyin_Catcher）设计文档

> **文档日期**：2026-07-11
> **状态**：待用户最终审阅
> **参考项目**：[Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)（仅参考设计思路，不作为运行时依赖）

---

## 1. 项目概述

### 1.1 背景

开源项目 `Douyin_TikTok_Download_API` 提供了抖音/TikTok 数据抓取的 API，但大部分用户不理解 API 如何使用。本项目旨在实现一个 **Windows 桌面端应用**，让用户通过简单配置即可下载抖音短视频（含图文、长视频）相关数据。

### 1.2 目标用户

公开发布给**非技术用户**。用户双击安装即可使用，无需命令行操作，Cookie 配置需有图文引导界面。

### 1.3 核心需求

- 支持抓取：视频/图集文件下载、视频元数据/文案、用户主页批量抓取
- 支持输入方式：单个链接、批量链接粘贴、用户主页链接自动抓取、文件导入链接列表
- 支持下载能力：批量下载、断点续传（任务队列续传 + 单文件分块续传）、多线程下载、失败自动重试（最多 3 次）
- Cookie 管理：支持单/多 Cookie 池，避免单个失效导致下载失败

### 1.4 与开源项目的关系

- **不 vendoring 其源码**，不 import 其模块
- 签名算法、解析逻辑参考其设计，但**完全自主实现**为本项目自有组件
- 仓库 README 中注明设计参考来源
- 外部依赖仅保留宽松协议的通用库（PySide6 LGPL、httpx BSD）

---

## 2. 架构总览

### 2.1 技术选型

| 层面 | 选型 | 理由 |
|---|---|---|
| UI 框架 | PySide6 (Qt) | 安装包小、单进程、性能好，QSS 可做现代简洁界面 |
| 爬虫语言 | Python | 与签名算法实现一致，httpx 异步支持好 |
| 数据库 | SQLite (WAL 模式) | 轻量、无需安装、足够支持任务持久化 |
| 打包 | PyInstaller --onedir + Inno Setup | onedir 启动快，Inno Setup 生成安装包 |
| HTTP 客户端 | httpx[http2] | 异步、支持 Range 分块续传 |

**不选 Electron/Tauri 的理由**：开源项目是 Python，方案 A 最大化复用、最小化体积（~60-80MB vs ~150-200MB）、最少进程间通信故障点，最适合公开发布给非技术用户。

### 2.2 架构图

```
┌──────────────────────────────────────────────────────┐
│                PySide6 单进程应用                      │
│                                                        │
│  ┌──────────────┐    信号/槽     ┌──────────────────┐ │
│  │  UI 层 (Qt)   │◄────────────►│  工作线程 (asyncio)│ │
│  │  - 主窗口     │   (线程安全)   │                    │ │
│  │  - 任务列表   │               │ ┌────────────────┐ │ │
│  │  - Cookie配置 │               │ │ 自主爬虫组件层  │ │ │
│  │  - 主页抓取   │               │ │ (本项目自有)    │ │ │
│  └──────────────┘               │ │ - 签名算法      │ │ │
│                                  │ │ - 链接解析      │ │ │
│                                  │ │ - 视频解析      │ │ │
│                                  │ │ - 主页抓取      │ │ │
│                                  │ │ - 无水印提取    │ │ │
│                                  │ └────────────────┘ │ │
│                                  │ ┌────────────────┐ │ │
│                                  │ │  下载引擎       │ │ │
│                                  │ │ (httpx+Range)  │ │ │
│                                  │ └────────────────┘ │ │
│                                  └──────────────────┘ │ │
│  ┌──────────────────────────────────────────────────┐ │
│  │       SQLite 持久化层 (任务/状态/元数据/Cookie池)   │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
打包: PyInstaller → 单 exe + SQLite db (~60-80MB)
```

### 2.3 线程模型

- **Qt 主线程**：跑 UI，响应用户操作
- **后台工作线程**：跑 asyncio 事件循环，承载爬虫调用和下载任务
- **通信方式**：Qt 信号/槽（`pyqtSignal`/`Signal`）线程安全通信
  - 工作线程发进度信号 → UI 线程更新进度条
  - UI 线程发"暂停/停止"信号 → 工作线程响应

### 2.4 并发控制

下载引擎用 `asyncio.Semaphore` 限制并发数，用户可配（默认 3，上限 10）。图集类型多图片在单项下载器内部再开子并发，也受总 Semaphore 约束。

### 2.5 运行时数据位置

程序目录只放代码和资源，用户数据放 `%APPDATA%/DouyinCatcher/`：
- `data.db` — SQLite 数据库（含任务、Cookie 池、应用配置）
- `logs/app.log` — 日志（按天滚动，保留 7 天）

卸载/重装不丢用户数据。

---

## 3. UI 界面设计

### 3.1 四个页面

应用采用左侧导航栏 + 右侧内容区布局，包含四个页面：

#### 页面 1：下载任务页（核心界面）

- 顶部批量操作：全部暂停 / 全部开始 / 清空已完成
- 任务列表，每行包含：
  - 缩略图
  - 标题 / 作者 / 日期 / 时长或图片数
  - 类型标签（视频 / 图文 / 长视频）
  - 进度条 + 百分比
  - 操作按钮（暂停 / 完成 / 失败）
- 底部状态栏：总数 · 下载中 · 已完成 · 失败
- 失败任务在行下方显示红色失败原因

#### 页面 2：链接抓取页

- 顶部多行文本框（粘贴链接，每行一个）+ "导入文件"按钮
- "开始解析"按钮
- 解析结果列表：每行 = 勾选框 | 缩略图 | 标题 | 作者 | 类型 | 时长/图片数
- 检测到用户主页链接时，显示过滤栏：
  - 类型（全部 / 视频 / 图文 / 长视频）
  - 数量上限
  - 时间段（起止日期）
- 全选 / 取消全选按钮 + 已选计数
- 底部：下载目录选择 + "开始下载"按钮

#### 页面 3：Cookie 配置页

- Cookie 列表（支持 Cookie 池）：
  - 每行：状态指示灯 | 标签 | 状态 | 最后使用时间 | [测试][删除]
  - 顶部：[+ 添加 Cookie] [全部测试] [教程]
  - 状态指示灯：绿点有效 / 红点失效 / 黄点未测试
- 添加 Cookie：弹窗输入 Cookie 内容 + 自定义标签
- 教程默认折叠，点"展开教程"显示图文步骤

#### 页面 4：设置页

- 下载目录（文件夹选择器）
- 并发下载数（滑块 1-10，默认 3）
- 单文件分块大小（默认 1MB）
- 失败重试次数（固定 3 次，不可改）
- 元数据保存格式（JSON / CSV 勾选）
- 导出日志按钮
- 关于 / 版本信息

### 3.2 视觉风格

- 简洁现代，QSS 样式表实现扁平化设计
- 左侧导航栏固定，右侧内容区随导航切换
- 进度条用品牌色（紫），完成用绿色，失败用红色
- 窗口可缩放，任务列表区域可滚动

---

## 4. 数据模型（SQLite）

### 4.1 表结构

```sql
-- 下载任务表（一次抓取/下载请求 = 一条记录）
CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type     TEXT NOT NULL,        -- 'single' | 'batch' | 'user_home' | 'file_import'
    source_url      TEXT,                 -- 原始链接（主页抓取时是主页 URL）
    status          TEXT NOT NULL,        -- 'pending'|'downloading'|'paused'|'completed'|'failed'
    total_items     INTEGER DEFAULT 0,    -- 该任务下的子项总数
    completed_items INTEGER DEFAULT 0,    -- 已完成子项数
    created_at      TEXT NOT NULL,        -- ISO8601
    updated_at      TEXT NOT NULL,
    download_dir    TEXT NOT NULL         -- 该任务的下载目录
);

-- 任务项表（一个视频/图集 = 一条记录，断点续传的核心）
CREATE TABLE task_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    aweme_id        TEXT,                 -- 抖音作品 ID
    url             TEXT NOT NULL,        -- 解析出的无水印直链
    title           TEXT,
    author          TEXT,                 -- 作者昵称
    author_sec_id   TEXT,                 -- 作者 sec_user_id
    type            TEXT NOT NULL,        -- 'video'|'image_set'|'long_video'
    duration        TEXT,                 -- '15s' | '12:30' | NULL
    image_count     INTEGER,              -- 图集图片数（图文类型才有）
    cover_url       TEXT,                 -- 封面图 URL（列表缩略图用）
    status          TEXT NOT NULL,        -- 'pending'|'downloading'|'paused'|'completed'|'failed'
    downloaded_bytes INTEGER DEFAULT 0,   -- 已下载字节数（单文件分块续传）
    total_bytes     INTEGER DEFAULT 0,    -- 文件总大小
    retry_count     INTEGER DEFAULT 0,    -- 已重试次数（上限 3）
    fail_reason     TEXT,                 -- 失败原因
    local_path      TEXT,                 -- 下载完成后的本地文件路径
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 作品元数据表（可选保存视频信息，用于数据分析）
CREATE TABLE metadata (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_item_id    INTEGER NOT NULL REFERENCES task_items(id) ON DELETE CASCADE,
    aweme_id        TEXT,
    title           TEXT,
    desc            TEXT,                 -- 视频文案
    author          TEXT,
    author_uid      TEXT,
    publish_time    TEXT,                 -- ISO8601
    like_count      INTEGER,
    comment_count   INTEGER,
    share_count     INTEGER,
    collect_count   INTEGER,
    tags            TEXT,                 -- JSON 数组，如 ["旅行","海边"]
    raw_json        TEXT                  -- 原始 API 返回（调试/扩展用）
);

-- Cookie 池表（支持多 Cookie 轮换）
CREATE TABLE cookies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT NOT NULL,        -- Cookie 字符串
    label       TEXT,                 -- 用户自定义标签，如"账号1"
    status      TEXT NOT NULL,        -- 'valid'|'invalid'|'untested'
    last_used   TEXT,                 -- 最后使用时间 ISO8601
    last_check  TEXT,                 -- 最后测试时间
    fail_count  INTEGER DEFAULT 0,    -- 连续失败次数
    created_at  TEXT NOT NULL
);

-- 应用配置表（键值对，存下载目录、并发数等非敏感配置）
CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

数据库开启 WAL 模式（`PRAGMA journal_mode=WAL`）提升并发写入性能。

### 4.2 断点续传实现

1. **任务队列续传**：应用启动时，扫描 `tasks` + `task_items` 中 `status IN ('pending','downloading','paused')` 的记录，重建下载队列。`downloading` 状态在重启后重置为 `paused`（上次中断了），等用户点"开始"或自动继续。

2. **单文件分块续传**：下载中断时，`task_items.downloaded_bytes` 已记录已下载字节数。下次继续时用 HTTP `Range: bytes={downloaded_bytes}-` 请求，从断点继续写入本地文件。本地文件以 `.part` 后缀临时保存，完成后去掉后缀。

3. **失败重试**：`retry_count` 每次失败 +1，达到 3 次后 `status` 改为 `failed`，`fail_reason` 记录原因，停止该子项重试。

### 4.3 Cookie 池使用策略

- 单 Cookie：等同于池里只有一条，直接用
- 多 Cookie：**轮询 + 健康检查**
  - 每次请求从池里取 `status='valid'` 且 `last_used` 最早的（最久未用优先，均衡负载）
  - 请求返回 461/412 → 该 Cookie `fail_count += 1`，连续失败 3 次置 `status='invalid'`
  - 某条 Cookie 失效时自动切换到池里下一条 valid 的，不打断下载
  - 池里所有 Cookie 都失效 → 暂停所有任务，弹窗提示"所有 Cookie 已失效，请更新"

---

## 5. 下载引擎

### 5.1 组件结构

```
┌─────────────── 工作线程 (asyncio loop) ───────────────┐
│                                                         │
│  ┌──────────────┐   ┌──────────────────────────────┐   │
│  │ 任务调度器    │──►│ 下载池 (Semaphore 并发控制)    │   │
│  │ Scheduler    │   │ - 从 SQLite 取 pending 项     │   │
│  │ - 维护待下载  │   │ - 并发数 = 用户配置 (1-10)    │   │
│  │   队列        │   └──────────────┬───────────────┘   │
│  │ - 暂停/恢复   │                  │                    │
│  └──────┬───────┘                  ▼                    │
│         │            ┌──────────────────────────────┐   │
│         │            │ 单项下载器 Downloader         │   │
│         │            │ - httpx Range 分块请求        │   │
│         │            │ - 写入 .part 文件             │   │
│         │            │ - 更新 downloaded_bytes       │   │
│         │            │ - 失败重试 (≤3次, 指数退避)    │   │
│         │            └──────────────┬───────────────┘   │
│         │                           │                    │
│         ▼                           ▼                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │  进度信号发射器 (pyqtSignal)                       │   │
│  │  - progress_updated(task_item_id, bytes, total)  │   │
│  │  - item_completed(task_item_id)                  │   │
│  │  - item_failed(task_item_id, reason)             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │ 信号 (线程安全)
         ▼
   UI 线程更新进度条/状态
```

### 5.2 单个任务项下载流程

1. 从 SQLite 取 `task_item`（status=pending/downloading），置为 `downloading`
2. 检查本地 `.part` 文件是否存在 → 读取已下载字节数 `downloaded_bytes`
3. 用 httpx 发 `Range: bytes={downloaded_bytes}-` 请求
4. 流式接收数据，每收到一块（如 64KB）：
   - 追加写入 `.part` 文件
   - 更新内存中的 `downloaded_bytes`
   - 每 5 秒或每 1MB 持久化一次 `downloaded_bytes` 到 SQLite（防止崩溃丢失进度）
   - 进度信号由进度汇报协程统一节流发送（见 5.5）
5. 下载完成 → `.part` 重命名为最终文件 → status=completed → 发 `item_completed` 信号

### 5.3 失败重试策略

- 网络异常 / HTTP 5xx / 被风控限流（HTTP 461/412）→ 触发重试
- `retry_count += 1`，等待 `2^retry_count` 秒（2s/4s/8s 指数退避）
- 达到 3 次 → status=failed，记录 `fail_reason` → 发 `item_failed` 信号
- HTTP 4xx（非限流）→ 直接失败，不重试（链接无效等）

### 5.4 暂停/恢复

- 暂停：调度器把目标项的 `asyncio.Task` 取消（`task.cancel()`），status 改为 `paused`，保留 `.part` 文件和 `downloaded_bytes`
- 恢复：重新创建 `asyncio.Task`，从 `paused` → `downloading`，走 Range 续传

### 5.5 进度信号节流

- 下载引擎内部用 `asyncio.Queue` 缓存进度更新
- 一个专门的"进度汇报协程"每 500ms 从 Queue 取最新值，批量发一次 `progress_updated` 信号
- UI 收到后只更新可见的进度条（QListView 模型只刷新可见行）

### 5.6 范围边界

- 下载引擎**只负责文件下载**，不负责链接解析（解析由爬虫组件层做，解析完写入 `task_items` 后才进下载队列）
- 同一 `aweme_id` 不重复下载：进队列前查 `task_items` 是否已有 completed 记录，有则跳过
- 不支持下载限速（YAGNI）

---

## 6. 爬虫组件层

自主实现，不依赖开源项目代码。参考其设计思路，用 httpx 异步请求抖音 Web API。

### 6.1 组件结构

```
┌─────────────────── 爬虫组件层 (crawlers/) ───────────────────┐
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ 链接解析器   │  │ 签名算法模块  │  │ 视频解析器            │ │
│  │ URLParser   │  │ Signer       │  │ VideoParser          │ │
│  │ - 提取 URL  │  │ - X-Bogus    │  │ - 调用 aweme/detail   │ │
│  │ - 识别类型  │  │ - A_Bogus    │  │ - 提取无水印直链      │ │
│  │             │  │ - msToken    │  │ - 提取封面/作者/时长  │ │
│  └─────────────┘  │ - verify_fp  │  └──────────────────────┘ │
│                    └──────────────┘                           │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ 主页抓取器             │  │ HTTP 客户端                  │ │
│  │ UserHomeCrawler      │  │ HttpClient                   │ │
│  │ - 输入 sec_user_id    │  │ - httpx.AsyncClient          │ │
│  │ - 分页拉取作品列表     │  │ - 注入 Cookie + 签名         │ │
│  │ - 类型/数量/时间过滤  │  │ - 统一 User-Agent/Headers    │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### 6.2 各组件职责

**URLParser（链接解析器）**
- 输入：用户粘贴的文本（可能含分享口令、短链、长链）
- 输出：`{type: 'video'|'image_set'|'long_video'|'user_home', url, aweme_id|sec_user_id}`
- 实现：正则提取 URL → httpx 跟随重定向拿到最终 URL → 解析查询参数
- 识别规则：
  - 含 `aweme_id` → 视频/图文/长视频（解析后才知道具体类型）
  - 含 `sec_user_id` 或 `/user/` → 用户主页
  - 抖音短链 `v.douyin.com/xxx` → 先重定向再判断

**Signer（签名算法模块）**——最核心、最易失效
- 职责：为请求 URL 生成 X-Bogus / A_Bogus / msToken 等签名参数
- 实现：参考 A-Bogus 算法的公开原理，用 Python 自主实现
- 接口：`sign(url: str, params: dict) -> dict`（返回需要追加的签名参数）
- 子模块：
  - `xbogus.py` - X-Bogus 签名
  - `abogus.py` - A_Bogus 签名
  - `mstoken.py` - msToken 生成
  - `verify_fp.py` - verify_fp / s_v_web_id 生成
- 维护策略：算法失效时只改这一个模块，不影响其他组件

**VideoParser（视频解析器）**
- 输入：`aweme_id` + Cookie
- 调用抖音 `aweme/v1/web/aweme/detail` 接口（经签名）
- 输出：`{type, title, author, duration, cover_url, no_watermark_url, image_urls[]}`
- 无水印提取逻辑：
  - 视频：从 `video.play_addr.url_list` 取无水印直链（或替换 playwm → play）
  - 图集：从 `images[].url_list` 取原图直链

**UserHomeCrawler（主页抓取器）**
- 输入：`sec_user_id` + Cookie + 过滤条件（类型/数量上限/时间段）
- 调用 `aweme/v1/web/aweme/post` 接口分页拉取
- 分页逻辑：维护 `max_cursor`，每页约 20 条，循环拉取直到无更多或达到上限
- 过滤：在内存中按 `create_time`（时间段）和 `aweme_type`（视频/图文）过滤
- 输出：作品列表 `[{aweme_id, title, cover_url, type, ...}]`，交给 UI 供用户勾选

**HttpClient（HTTP 客户端）**
- 封装 httpx.AsyncClient 单例
- 统一注入：Cookie（从 Cookie 池取）、User-Agent、Referer、签名参数
- 超时配置：连接 10s，读取 30s
- 错误分类：网络异常 / HTTP 状态码 / 风控响应

### 6.3 风控应对

原项目不提供任何验证解决方案（文档明确写"你需要自行解决爬虫Cookie风控问题"）。本项目同样不实现自动过验证，遇到即标记失败：

| 响应特征 | 判断 | 处理 |
|---|---|---|
| HTTP 461 / 412 | Cookie 失效或被限流 | 该任务项标记失败，fail_reason = "Cookie 失效或被限流，请更新 Cookie" |
| 响应含滑动验证 HTML | 触发滑块验证 | 该任务项标记失败，fail_reason = "触发抖音验证，无法下载" |
| HTTP 200 但 `status_code` 字段非 0 | API 层面拒绝 | 标记失败，fail_reason 记录返回的错误信息 |
| 正常 200 + 有效数据 | 成功 | 正常处理 |

Cookie 有效性由用户自己维护，应用在 Cookie 页提供"测试 Cookie"按钮让用户主动验证。

**"测试 Cookie"验证逻辑**：用该 Cookie 调用一个轻量抖音 API（如获取当前登录用户信息接口），若返回 HTTP 200 且响应 JSON 中 `status_code == 0`，则判定 Cookie 有效（`status='valid'`）；否则判定无效（`status='invalid'`），并显示具体错误。

### 6.4 错误传播

爬虫层抛出明确的异常类型，下载引擎/UI 层据此决定行为：
- `CookieInvalidError` → 跳转 Cookie 配置页
- `RateLimitedError` → 该项标记失败，原因提示等待
- `VideoNotFoundError`（作品已删除/私密）→ 标记该项失败，原因写明
- `NetworkError` → 交给下载引擎的重试逻辑

### 6.5 测试策略

- 签名算法：用已知输入/输出对验证（从开源项目抓取测试用例作为参考）
- 链接解析器：纯函数，覆盖各种分享文本格式
- 视频解析器/主页抓取器：用 VCR.py 录制真实响应做单元测试，避免每次测试都打真实 API

---

## 7. 错误处理与用户体验

### 7.1 核心原则

面向非技术用户：**绝不让用户看到原始异常栈，每个错误都要有人话解释 + 下一步建议**。

### 7.2 错误分类与用户可见信息

| 错误类型 | 触发场景 | 用户看到的 | 用户该做什么 |
|---|---|---|---|
| Cookie 无效/过期 | 签名请求返回 461/412，或"测试 Cookie"失败 | "Cookie 已失效，抖音需要重新登录验证" | 跳转 Cookie 配置页，按教程重新获取 |
| 网络连接失败 | httpx 连接超时/DNS 失败 | "网络连接失败，请检查网络后重试" | 检查网络，点"重试" |
| 视频不存在/已删除 | aweme/detail 返回 status_code 非 0 | "该作品已被删除或设为私密，无法下载" | 跳过该项 |
| 触发验证 | 响应含滑动验证 HTML | "抖音要求安全验证，暂时无法下载此作品" | 稍后重试，或更新 Cookie |
| 下载失败（3次重试后） | 重试耗尽 | "下载失败：{具体原因}（已重试 3 次）" | 检查原因后可手动重新加入队列 |
| 磁盘空间不足 | 写入 .part 文件时 OSError | "磁盘空间不足，无法保存到 {目录}" | 更换下载目录或清理磁盘 |
| 链接格式错误 | URLParser 无法识别 | "无法识别该链接，请确认是抖音视频/主页链接" | 检查链接格式 |
| 未知错误 | 未预期的异常 | "发生未知错误：{简短描述}" | 可点"复制详情"反馈给开发者 |

### 7.3 错误展示位置

- **任务项级错误**：显示在该任务行下方（红色小字），不打断其他任务
- **全局错误**（Cookie 全部失效、磁盘满）：弹窗提示 + 提供操作按钮
- **输入错误**（链接格式）：输入框下方红字提示，不弹窗

### 7.4 首次使用引导

```
应用首次启动
     │
     ▼
[欢迎页] 简短介绍应用功能
     │
     ▼
[设置下载目录] 默认 %USERPROFILE%/Downloads/DouyinCatcher，可改
     │
     ▼
[配置 Cookie] 图文教程：添加第一个 Cookie 并测试通过
     │
     ▼
[完成] 进入主界面（下载任务页）
```

- 引导状态记录在 `config` 表（`key='onboarding_done'`）
- 后续启动直接进主界面

### 7.5 Cookie 教程内容

折叠式图文步骤，内嵌在 Cookie 配置页。每步标注截图需求，图片由用户提供，放 `assets/cookie_tutorial/`：

1. **打开抖音网页版**：浏览器访问 https://www.douyin.com 并登录
   - 📷 需要截图：浏览器打开 douyin.com 已登录状态的页面 → `step1.png`
2. **打开开发者工具**：按 F12 键，切到"Network"（网络）标签
   - 📷 需要截图：F12 打开后 Network 标签的界面 → `step2.png`
3. **刷新页面**：按 F5 刷新，让请求列表出现
   - 📷 需要截图：刷新后 Network 列表出现多条请求的界面 → `step3.png`
4. **找到任意请求**：在请求列表里点任意一条 douyin.com 的请求
   - 📷 需要截图：点击某条请求后右侧出现 Headers 面板的界面 → `step4.png`
5. **复制 Cookie**：在 Request Headers 里找到 `Cookie` 字段，右键复制完整值
   - 📷 需要截图：Headers 面板里 Cookie 字段被高亮/选中的界面 → `step5.png`
6. **粘贴到左侧**：把复制的 Cookie 粘贴到添加 Cookie 弹窗的文本框
   - 📷 需要截图：应用添加 Cookie 弹窗，Cookie 已粘贴进文本框的状态 → `step6.png`
7. **点"测试 Cookie"**：验证是否有效
   - 📷 需要截图：测试通过后显示"Cookie 有效"的状态 → `step7.png`

### 7.6 操作反馈

- 所有耗时操作（解析链接、测试 Cookie、主页抓取）显示 loading 状态 + 可取消
- 批量操作（全部暂停/开始）立即响应，不阻塞 UI
- 任务状态变化有视觉反馈（进度条动画、状态颜色变化）
- 不使用系统通知/弹窗轰炸用户，所有信息在应用内展示

### 7.7 日志

- 日志文件：`%APPDATA%/DouyinCatcher/logs/app.log`（按天滚动，保留 7 天）
- 记录：API 请求/响应摘要、异常栈、任务状态变化
- 用户看不到日志，但"设置"页有"导出日志"按钮（方便反馈问题时给开发者）

---

## 8. 项目结构与打包

### 8.1 项目目录结构

```
Douyin_Catcher/
├── main.py                          # 入口：启动 QApplication
├── app/
│   ├── __init__.py
│   ├── config.py                    # 全局配置常量（APPDATA 路径、默认值）
│   ├── database.py                  # SQLite 连接管理、表初始化、迁移
│   ├── models.py                    # 数据模型（Task, TaskItem, Cookie, Metadata）
│   └── logger.py                    # 日志配置（按天滚动）
├── ui/
│   ├── __init__.py
│   ├── main_window.py               # 主窗口（导航栏 + 页面切换）
│   ├── pages/
│   │   ├── download_page.py         # 下载任务页
│   │   ├── fetch_page.py            # 链接抓取页
│   │   ├── cookie_page.py           # Cookie 配置页（含池管理）
│   │   ├── settings_page.py         # 设置页
│   │   └── onboarding_page.py       # 首次引导
│   ├── widgets/
│   │   ├── task_item_widget.py      # 任务行组件（缩略图+进度条+状态）
│   │   ├── cookie_item_widget.py    # Cookie 列表行组件
│   │   └── filter_bar.py            # 主页抓取过滤栏
│   └── assets/
│       ├── style.qss                # 全局 QSS 样式表
│       └── cookie_tutorial/
│           ├── step1.png ~ step7.png  # 教程截图（用户提供）
├── crawlers/                        # 自主爬虫组件层
│   ├── __init__.py
│   ├── http_client.py               # httpx 封装 + Cookie 池注入
│   ├── url_parser.py                # 链接解析器
│   ├── signer/                      # 签名算法模块
│   │   ├── __init__.py
│   │   ├── xbogus.py
│   │   ├── abogus.py
│   │   ├── mstoken.py
│   │   └── verify_fp.py
│   ├── video_parser.py              # 视频解析器
│   ├── user_home_crawler.py         # 主页抓取器
│   └── exceptions.py                # 异常类型定义
├── downloader/                      # 下载引擎
│   ├── __init__.py
│   ├── scheduler.py                 # 任务调度器（队列 + 暂停/恢复）
│   ├── downloader.py                # 单项下载器（Range + 重试）
│   └── progress_reporter.py         # 进度信号节流
├── worker/
│   ├── __init__.py
│   └── async_worker.py              # 后台工作线程（跑 asyncio loop + 信号桥接）
├── assets/
│   └── icon.ico                     # 应用图标
├── tests/
│   ├── test_url_parser.py
│   ├── test_signer.py
│   ├── test_downloader.py
│   └── fixtures/                    # VCR.py 录制的响应
├── pyproject.toml                   # 项目元数据 + 依赖 + pytest/cov 配置
├── requirements.txt                 # 运行依赖
├── requirements-dev.txt             # 开发依赖（pytest, vcrpy 等）
├── .gitignore                       # 含 .env（测试 Cookie）
└── README.md
```

### 8.2 分层职责边界

| 层 | 目录 | 职责 | 依赖 |
|---|---|---|---|
| UI 层 | `ui/` | 画界面、响应用户操作、发信号 | models, worker |
| 工作线程 | `worker/` | 跑 asyncio loop，桥接 UI 信号与异步任务 | downloader, crawlers |
| 下载引擎 | `downloader/` | 并发下载、分块续传、重试、进度汇报 | models |
| 爬虫层 | `crawlers/` | 链接解析、签名、视频解析、主页抓取 | http_client |
| 数据层 | `app/` (database, models) | SQLite 持久化、配置 | 无 |

依赖方向单向：UI → worker → {downloader, crawlers} → models → database。下层不依赖上层，避免循环依赖。

### 8.3 依赖清单

**运行依赖**（`requirements.txt`）：
```
PySide6>=6.6
httpx[http2]>=0.27
```

**开发依赖**（`requirements-dev.txt`）：
```
pytest
pytest-asyncio
pytest-cov
vcrpy
respx
ruff
black
```

### 8.4 打包

PyInstaller `--onedir` 模式（启动快于 onefile）：

```
PyInstaller --onedir --windowed --name DouyinCatcher
            --icon assets/icon.ico
            --add-data "ui/assets;ui/assets"
            --add-data "assets;assets"
            main.py
```

产物：`dist/DouyinCatcher/` 目录（含 exe + 依赖），用 Inno Setup 打成安装包 `DouyinCatcher_Setup.exe`。

---

## 9. 测试与质量规范

### 9.1 测试 Cookie 使用规范

- 测试所需 Cookie **由用户提供，不硬编码、不提交到仓库**
- 测试用 Cookie 存放在本地 `.env` 文件（已加入 `.gitignore`）
- **测试全流程完成后必须清除**：测试脚本结束前主动删除 Cookie 痕迹，CI 环境不留存任何 Cookie
- VCR.py 录制的响应 fixture 在提交前需人工核对，确保不含敏感 Cookie 字段（录制时自动擦除 `Cookie` / `Set-Cookie` 头）

### 9.2 覆盖率要求（硬性指标）

| 指标 | 要求 |
|---|---|
| 代码行覆盖率 | **≥ 80%** |
| 方法覆盖率 | **≥ 30%** |
| 签名算法模块 (`crawlers/signer/`) | 行覆盖率 ≥ 90%（核心组件，最高标准） |
| 下载引擎 (`downloader/`) | 行覆盖率 ≥ 80% |
| 爬虫层 (`crawlers/`) | 行覆盖率 ≥ 75%（依赖外部 API，用 VCR.py 录制回放） |
| UI 层 (`ui/`) | 不强制覆盖率（Qt 组件难单测，重点靠手动验收） |

覆盖率工具：`pytest-cov`，配置在 `pyproject.toml`：
```toml
[tool.pytest.ini_options]
addopts = "--cov=. --cov-report=term-missing --cov-report=html --cov-fail-under=80"
```

### 9.3 CI/CD 设计（保留设计，暂不实现）

**CI 流程（GitHub Actions，待接入）**：
```
PR 提交
  ├─ 代码检查：ruff (lint) + black --check (格式)
  ├─ 单元测试：pytest --cov
  │   ├─ 行覆盖率 < 80% → 失败
  │   └─ 方法覆盖率 < 30% → 失败
  ├─ 安全扫描：检查是否有 Cookie / 密钥泄漏（gitleaks）
  └─ 构建验证：PyInstaller 打包能否成功（不发布）
```

**CD 流程（Release 时手动触发）**：
```
打 tag (v1.0.0)
  ├─ PyInstaller 打包
  ├─ Inno Setup 生成安装包
  └─ 上传到 GitHub Release
```

### 9.4 PR 开发要求

1. 每个 PR 必须包含对应测试
2. 行覆盖率 ≥ 80%，方法覆盖率 ≥ 30%，否则 CI 阻断合并
3. 签名算法变更必须附带已知输入/输出对的测试用例
4. 不得在代码、测试、日志中硬编码 Cookie
5. 提交前运行 `pytest` 确保全部通过
6. Cookie 相关测试用 VCR.py 录制回放，不依赖实时 Cookie（实时 Cookie 仅用于本地手动验证算法有效性）

### 9.5 测试策略分层

| 层级 | 方法 | 工具 |
|---|---|---|
| 签名算法 | 已知输入/输出对单元测试 | pytest |
| 链接解析器 | 纯函数单元测试，覆盖各种分享文本 | pytest |
| 爬虫层（视频解析/主页抓取） | VCR.py 录制真实响应回放，不打真实 API | pytest + vcrpy |
| 下载引擎 | mock httpx 响应，测试分块续传/重试/暂停逻辑 | pytest + respx |
| 数据层 | 临时 SQLite 内存数据库测试 | pytest |
| UI 层 | 手动验收（不强制自动化） | 人工 |
