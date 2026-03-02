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

from ctfile_downloader.api import CaptchaError, CtfileAPI, CtfileAPIError, LinkExpiredError, RateLimitError
from ctfile_downloader.aria2_rpc import Aria2RpcClient
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


def download_file_aria2c(
    url: str,
    dest: Path,
    aria2c: Aria2RpcClient,
) -> bool:
    """使用 aria2c JSON-RPC 下载单个文件，通过轮询状态驱动 Rich 进度条。"""
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        gid = aria2c.add_uri(url, dest.parent, dest.name)
    except RuntimeError as e:
        console.print(f"  [red]aria2c 添加下载失败: {e}[/red]")
        return False

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
            total=None,
            completed=0,
            filename=dest.name[:30],
        )

        while True:
            try:
                status = aria2c.tell_status(gid)
            except RuntimeError as e:
                console.print(f"  [red]aria2c 状态查询失败: {e}[/red]")
                return False

            state = status["status"]
            total = int(status.get("totalLength", 0))
            completed = int(status.get("completedLength", 0))

            if state == "complete":
                progress.update(task, completed=total, total=total or None)
                return True
            elif state == "error":
                msg = status.get("errorMessage", "未知错误")
                console.print(f"  [red]aria2c 下载错误: {msg}[/red]")
                return False

            progress.update(task, completed=completed, total=total or None)
            time.sleep(0.5)


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


def _refresh_folder_entries(
    api: CtfileAPI,
    file_tree: list[tuple[str, FileEntry]],
    start_index: int,
    folder_id: str,
    fk: str,
) -> int:
    """重新获取文件夹列表，批量更新所有来自该文件夹的待下载文件的 code。

    Returns: 更新的条目数量。
    """
    folder_info = api.get_folder_info(folder_id, fk)
    list_url = folder_info["file"]["url"]
    fresh_entries = api.get_file_list(list_url)

    fresh_codes = {e.name: e.code for e in fresh_entries if not e.is_folder}

    updated = 0
    for idx in range(start_index, len(file_tree)):
        _, entry = file_tree[idx]
        if entry.parent_folder_id == folder_id and entry.parent_fk == fk:
            if entry.name in fresh_codes:
                entry.code = fresh_codes[entry.name]
                updated += 1
    return updated


def batch_download(
    api: CtfileAPI,
    file_tree: list[tuple[str, FileEntry]],
    output_dir: Path,
    aria2c: Aria2RpcClient | None = None,
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
            result = get_download_url_with_retry(api, entry.code)
            if not result[0]:
                stats.failed += 1
                stats.failed_files.append(rel_path)
                consecutive_errors += 1
                continue

            download_url, file_info = result
            if aria2c:
                success = download_file_aria2c(download_url, dest, aria2c)
            else:
                success = download_file(download_url, dest)
            if success:
                stats.success += 1
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    api.reset_delay()
            else:
                stats.failed += 1
                stats.failed_files.append(rel_path)
                consecutive_errors += 1

        except LinkExpiredError:
            console.print(f"  [yellow]文件码已过期，正在刷新文件夹列表...[/yellow]")
            try:
                refreshed = _refresh_folder_entries(
                    api, file_tree, i - 1, entry.parent_folder_id, entry.parent_fk,
                )
                console.print(f"  [green]已刷新 {refreshed} 个文件码[/green]")
            except CtfileAPIError as refresh_err:
                console.print(f"  [red]刷新文件夹失败: {refresh_err}[/red]")
                stats.failed += 1
                stats.failed_files.append(rel_path)
                consecutive_errors += 1
                continue

            # 用刷新后的 code 重试当前文件
            try:
                result = get_download_url_with_retry(api, entry.code)
                if not result[0]:
                    stats.failed += 1
                    stats.failed_files.append(rel_path)
                    consecutive_errors += 1
                    continue

                download_url, file_info = result
                if aria2c:
                    success = download_file_aria2c(download_url, dest, aria2c)
                else:
                    success = download_file(download_url, dest)
                if success:
                    stats.success += 1
                    if consecutive_errors > 0:
                        consecutive_errors = 0
                        api.reset_delay()
                else:
                    stats.failed += 1
                    stats.failed_files.append(rel_path)
                    consecutive_errors += 1
            except CtfileAPIError as e:
                console.print(f"  [red]刷新后仍然失败: {e}[/red]")
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
