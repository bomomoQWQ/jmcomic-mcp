# jmcomic-mcp

禁漫天堂 MCP 服务器 — 搜索、下载、管理漫画，基于 Model Context Protocol。

> 基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 原生 async API，支持 stdio 和 streamable HTTP 双传输模式。

## 快速开始

```bash
git clone https://github.com/bomomoQWQ/jmcomic-mcp.git
cd jmcomic-mcp
uv sync

# stdio 模式（Claude Desktop 等本地 MCP 客户端）
uv run jmcomic-mcp

# HTTP 模式（AstrBot 等远程 MCP 客户端）
uv run jmcomic-mcp --http 8003
```

## 工具列表（10 个）

### 浏览发现（4 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `search` | 关键词搜索 | `query`, `category`, `time`, `sort`, `page` |
| `album_detail` | 专辑详情 + 章节列表 | `album_id` |
| `ranking` | 周榜/月榜/总榜 | `period` |
| `browse` | 按分类浏览（无关键词） | `category`, `time`, `sort`, `page` |

### 下载管理（4 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `download` | 下载 + 自动转 PDF，后台异步，一次只跑一个 | `album_id` |
| `download_status` | 查看进度、已下载页数、耗时 | `album_id` |
| `download_list` | 列出全部下载记录 | — |
| `cleanup` | 清理文件，删原图留 PDF 或全清 | `album_id`, `keep_pdf` |

### 文件交付（2 个）

| 工具 | 功能 | 参数 |
|---|---|---|
| `files_list` | 列出所有 PDF + MD5 短名链接 | — |
| `file_url` | 按专辑 ID 查下载链接 | `album_id` |

### 分类 / 排序 / 时间

| 分类 | 排序 | 时间 |
|---|---|---|
| `all` `doujin` `single` `short` `another` `hanman` `meiman` `doujin_cosplay` `3d` `english_site` | `latest` `view` `picture` `like` | `all` `today` `week` `month` |

## 配置

### op.yml（可选）

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
| `FILE_SERVER_URL` | 文件下载链接的基础 URL | `http://192.168.1.10:8889` |

### MCP 客户端配置

```json
{
  "mcpServers": {
    "jmcomic": {
      "transport": "streamable_http",
      "url": "http://192.168.1.10:8003/mcp",
      "timeout": 30,
      "sse_read_timeout": 300
    }
  }
}
```

## 文件服务器

下载的 PDF 通过独立文件服务器对外提供，运行在 `:8889`：

- 短名基于文件名 MD5 前 6 位（如 `bf258b.pdf`），每次下载不同名，无冲突
- 动态列表页 `http://192.168.1.10:8889/` 显示所有可下载文件
- 正确设置 `Content-Disposition` 头，兼容 LANraragi `download_url`
- systemd 服务：`fileserver.service`

## 架构

```
jmcomic-mcp/
├── pyproject.toml
└── src/jmcomic_mcp/
    ├── __init__.py
    ├── server.py          # FastMCP + 10 工具
    └── fileserver.py      # HTTP 文件服务器（独立进程）
```

## 设计特点

- **原生异步**：浏览和查询直调 `jmcomic.AsyncJmApiClient`，不阻塞事件循环
- **懒加载初始化**：JM 客户端首次调用时才创建，避免启动时崩溃
- **域名自动更新**：bytepluses CDN 拉取最新 API 域名
- **代理支持**：`HTTP_PROXY` / `HTTPS_PROXY` 环境变量透传
- **并发控制**：Semaphore(1) 一次只跑一个下载，限 2 图片线程，弱 CPU 不卡死
- **PIL PDF 转换**：递归合并子目录处理多章节本子，兼容 webp
- **MD5 短名**：文件名哈希前 6 位，不上传不重复
- **下载进度追踪**：实时轮询文件数，含已用时和已下载页数

## 运行环境

- Python ≥ 3.10
- 能访问 JM CDN 的网络（或配代理）
- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)
- `mcp >= 1.0.0`

## License

MIT
