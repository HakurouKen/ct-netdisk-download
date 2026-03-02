from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ctfile_downloader.api import CaptchaError, CtfileAPI, CtfileAPIError, RateLimitError
from ctfile_downloader.parser import FileEntry

console = Console()


@dataclass
class DownloadStats:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    failed_files: list[str] = field(default_factory=list)


def download_file(
    url: str,
    dest: Path,
    client: httpx.Client | None = None,
) -> bool:
    """下载单个文件，支持断点续传。"""
    dest.parent.mkdir(parents=True, exist_ok=True)

    headers: dict[str, str] = {}
    initial_size = 0

    if dest.exists():
        initial_size = dest.stat().st_size
        headers["Range"] = f"bytes={initial_size}-"

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=60.0, follow_redirects=True)

    try:
        with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 200 and initial_size > 0:
                initial_size = 0
            elif resp.status_code == 416:
                console.print(f"  [dim]文件可能已完成，跳过[/dim]")
                return True

            total = int(resp.headers.get("content-length", 0)) + initial_size
            mode = "ab" if resp.status_code == 206 else "wb"

            with Progress(
                TextColumn("[bold blue]{task.fields[filename]}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "downloading",
                    total=total or None,
                    completed=initial_size,
                    filename=dest.name[:30],
                )
                with open(dest, mode) as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

        return True
    except (httpx.HTTPError, OSError) as e:
        console.print(f"  [red]下载错误: {e}[/red]")
        return False
    finally:
        if own_client:
            client.close()


def get_download_url_with_retry(
    api: CtfileAPI,
    file_code: str,
    max_retries: int = 5,
) -> tuple[str, dict] | tuple[None, None]:
    """获取下载链接，遇到验证码/限频自动重试。每次重试都重新获取 file_info（verifycode 有时效性）。"""
    for attempt in range(1, max_retries + 1):
        try:
            file_info = api.get_file_info(file_code)
            if attempt == 1:
                file_name = file_info.get("file_name", "?")
                console.print(f"  文件: {file_name} ({file_info.get('file_size', '?')})")
            url = api.get_download_url(file_info)
            return url, file_info
        except RateLimitError as e:
            wait = 60
            console.print(f"  [yellow]被限频: {e}，等待 {wait}s 后重试 ({attempt}/{max_retries})[/yellow]")
            time.sleep(wait)
        except CaptchaError as e:
            if attempt < max_retries:
                wait = 10 + attempt * 5
                console.print(
                    f"  [yellow]获取下载链接失败: {e}，等待 {wait}s 后重试 ({attempt}/{max_retries})[/yellow]"
                )
                time.sleep(wait)
            else:
                console.print(
                    f"  [red]多次重试失败。请在浏览器中访问城通网盘完成验证后重新运行。[/red]"
                )
                return None, None
        except CtfileAPIError:
            raise  # 文件不存在、过期等不可重试错误，向上抛出

    return None, None


# 连续失败阈值：超过此数则认为被限频
_CONSECUTIVE_FAIL_THRESHOLD = 3


def batch_download(
    api: CtfileAPI,
    file_tree: list[tuple[str, FileEntry]],
    output_dir: Path,
) -> DownloadStats:
    """批量下载，带连续失败检测和自适应限频处理。"""
    stats = DownloadStats()
    total = len(file_tree)
    consecutive_errors = 0

    for i, (rel_path, entry) in enumerate(file_tree, 1):
        dest = output_dir / rel_path
        console.print(f"\n[bold][{i}/{total}][/bold] {rel_path}")

        if dest.exists() and dest.stat().st_size > 0:
            console.print(f"  [dim]已存在，跳过[/dim]")
            stats.skipped += 1
            continue

        # 连续失败过多时，暂停较长时间并增大后续请求间隔
        if consecutive_errors >= _CONSECUTIVE_FAIL_THRESHOLD:
            wait = min(30 * consecutive_errors, 300)
            console.print(
                f"\n  [bold yellow]⚠ 连续 {consecutive_errors} 次失败，疑似被限频，暂停 {wait}s...[/bold yellow]"
            )
            time.sleep(wait)
            api.increase_delay(10.0)

        try:
            download_url, file_info = get_download_url_with_retry(api, entry.code)
            if not download_url:
                stats.failed += 1
                stats.failed_files.append(rel_path)
                consecutive_errors += 1
                continue

            success = download_file(download_url, dest)
            if success:
                stats.success += 1
                # 成功时逐步恢复延迟
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    api.reset_delay()
            else:
                stats.failed += 1
                stats.failed_files.append(rel_path)
                consecutive_errors += 1

        except CtfileAPIError as e:
            console.print(f"  [red]API 错误: {e}[/red]")
            stats.failed += 1
            stats.failed_files.append(rel_path)
            consecutive_errors += 1
        except Exception as e:
            console.print(f"  [red]未知错误: {e}[/red]")
            stats.failed += 1
            stats.failed_files.append(rel_path)
            consecutive_errors += 1

    return stats
