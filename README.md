# ctfile-downloader

城通网盘（ctfile.com）通用下载器，支持文件夹批量下载和单文件下载。

## 功能

- **文件夹批量下载** — 递归遍历共享文件夹，一键下载全部文件
- **单文件下载** — 直接下载单个文件链接
- **断点续传** — 基于 HTTP Range 自动恢复中断的下载
- **验证码/限流处理** — 自动重试，指数退避
- **过期链接刷新** — 批量下载时自动刷新过期的临时文件码
- **密码支持** — 支持加密分享链接
- **Rich 终端界面** — 进度条、下载速度、文件列表预览

## 安装

需要 Python 3.12+，推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
git clone <repo-url>
cd ct-netdisk-download
uv sync
```

## 使用

### 下载共享文件夹

```bash
uv run ctdl "https://url01.ctfile.com/d/11449240-33792850-725200?d=33792850&fk=387c4e"
```

### 下载单个文件

```bash
uv run ctdl "https://url01.ctfile.com/f/12345-67890-abcdef"
```

### 完整参数

```
用法: ctdl [OPTIONS] URL

参数:
  URL                        ctfile.com 分享链接（/d/ 或 /f/）

选项:
  -p, --password TEXT        访问密码（默认为空）
  -o, --output DIRECTORY     输出目录（默认: downloads）
  --delay-min FLOAT          请求最小间隔秒数（默认: 3.0）
  --delay-max FLOAT          请求最大间隔秒数（默认: 8.0）
```

### 示例

```bash
# 带密码下载
uv run ctdl "https://url01.ctfile.com/d/..." -p mypassword

# 指定输出目录和请求间隔
uv run ctdl "https://url01.ctfile.com/d/..." -o ./my_downloads --delay-min 2.0 --delay-max 6.0
```

## 项目结构

```
src/ctfile_downloader/
├── main.py          # CLI 入口（click）
├── api.py           # ctfile.com API 客户端
├── downloader.py    # 下载引擎（断点续传、重试、批量下载）
└── parser.py        # URL 解析 & 文件列表解析
```

## 开发

```bash
# 运行测试
uv run pytest tests/ -v
```

## 依赖

| 库 | 用途 |
|---|---|
| [httpx](https://www.python-httpx.org/) | HTTP 客户端 |
| [rich](https://rich.readthedocs.io/) | 终端 UI |
| [click](https://click.palletsprojects.com/) | CLI 框架 |
