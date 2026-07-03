# jmcomic-mcp

禁漫天堂 MCP 服务器 — 搜索、下载、管理漫画，基于 Model Context Protocol。

> 基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 原生 async API，支持 stdio 和 streamable HTTP 双传输模式。

## 快速开始

```bash
git clone <repo-url> jmcomic-mcp
cd jmcomic-mcp
uv sync

# stdio 模式（Claude Desktop 等本地 MCP 客户端）
uv run jmcomic-mcp

# HTTP 模式（AstrBot 等远程 MCP 客户端）
uv run jmcomic-mcp --http 8003
```

## 工具列表

### 浏览发现（4 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `search` | 关键词搜索 | `query`, `category`, `time`, `sort`, `page` |
| `album_detail` | 专辑详情 + 章节列表 | `album_id` |
| `album_comments` | 查看专辑评论区 | `album_id`, `page` |
| `ranking` | 周榜/月榜/总榜 | `period` |
| `browse` | 按分类浏览（无关键词） | `category`, `time`, `sort`, `page` |

### 下载管理（4 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `download` | 下载专辑，后台异步执行 | `album_id` |
| `download_status` | 查看下载进度和状态 | `album_id` |
| `download_list` | 列出全部下载记录 | — |
| `cleanup` | 清理下载文件，删原图留 PDF 或全清 | `album_id`, `keep_pdf` |

### 文件交付（2 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `files_list` | 列出所有已下载 PDF + 下载链接 | — |
| `file_url` | 按专辑 ID 查 PDF 下载链接 | `album_id` |

## 配置

### op.yml（可选）

工作目录下放 `op.yml`，不写就用默认值：

```yaml
client:
  impl: api              # api=移动端接口（推荐），html=网页爬虫（兜底）
  retry_times: 3
  postman:
    meta_data:
      timeout: 30

dir_rule:
  base_dir: ~/downloads  # 下载目录
```

### 环境变量

| 变量 | 作用 | 默认值 |
|---|---|---|
| `HTTP_PROXY` | JM API 请求代理 | — |
| `HTTPS_PROXY` | 同上 | — |
| `JM_OPTION_PATH` | op.yml 路径 | `./op.yml` |
| `FILE_SERVER_URL` | 文件下载链接的基础 URL | — |

### MCP 客户端配置

```json
{
  "mcpServers": {
    "jmcomic": {
      "transport": "streamable_http",
      "url": "http://<服务器IP>:8003/mcp",
      "timeout": 30,
      "sse_read_timeout": 300
    }
  }
}
```

## 架构

```
jmcomic-mcp/
├── pyproject.toml
└── src/jmcomic_mcp/
    ├── __init__.py
    └── server.py          # FastMCP + 11 工具，单文件 ~500 行
```

### 设计特点

- **原生异步**：浏览和查询操作直调 `jmcomic.AsyncJmApiClient`，充分利用 Python asyncio，不阻塞事件循环
- **懒加载初始化**：JM 客户端在首次工具调用时才创建，避免启动时网络不通导致整个进程崩溃
- **域名自动更新**：启动时自动从 bytepluses CDN 拉取最新 API 域名列表，无需手动维护
- **下载状态追踪**：每个下载任务有完整的生命周期——queued → downloading → done / failed，随时可查进度
- **代理支持**：通过 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量透传，无需改代码
- **空间管理**：`cleanup` 一键删除下载留下的原始图片，只保留 PDF，节省磁盘空间
- **文件交付**：`files_list` + `file_url` 直接给出可访问的下载链接，对接 HTTP 文件服务器

## 运行环境

- Python ≥ 3.10
- 能访问 JM CDN 的网络（或配代理）
- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
- `mcp >= 1.0.0`

## License

MIT
