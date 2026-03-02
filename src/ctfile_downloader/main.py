from __future__ import annotations

import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ctfile_downloader.api import CtfileAPI
from ctfile_downloader.aria2_rpc import Aria2RpcClient
from ctfile_downloader.downloader import batch_download, download_file, download_file_aria2c, get_download_url_with_retry
from ctfile_downloader.parser import parse_share_url

console = Console()


def _count_root_items(file_tree: list[tuple[str, object]]) -> int:
    """统计文件树中不同的根级条目（文件或一级文件夹）数量。"""
    roots = set()
    for rel_path, _ in file_tree:
        roots.add(rel_path.split("/")[0])
    return len(roots)


@click.command()
@click.argument("url")
@click.option(
    "-p",
    "--password",
    type=str,
    default="",
    help="共享文件夹/文件的访问密码",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="下载目录（默认: 当前目录）",
)
@click.option(
    "--delay-min",
    type=float,
    default=3.0,
    help="请求间最小延迟秒数（默认: 3.0）",
)
@click.option(
    "--delay-max",
    type=float,
    default=8.0,
    help="请求间最大延迟秒数（默认: 8.0）",
)
@click.option(
    "--aria2c",
    "use_aria2c",
    is_flag=True,
    default=False,
    help="使用 aria2c 进行多线程下载（需要系统已安装 aria2c）",
)
@click.option(
    "--threads",
    type=int,
    default=4,
    help="aria2c 每个文件的连接数（默认: 4，仅在 --aria2c 启用时有效）",
)
def cli(url: str, password: str, output: str | None, delay_min: float, delay_max: float, use_aria2c: bool, threads: int) -> None:
    """城通网盘通用下载器

    URL: 城通网盘共享链接（支持文件夹 /d/ 和单文件 /f/）
    """
    output_explicit = output is not None
    output_dir = Path(output).resolve() if output_explicit else Path(".").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    share_info = parse_share_url(url)
    console.print(f"[bold]共享链接:[/bold] {url}")
    console.print(f"[bold]链接类型:[/bold] {'文件夹' if share_info.link_type == 'folder' else '单文件'}")
    console.print(f"[bold]Share Code:[/bold] {share_info.share_code}")
    if share_info.folder_id:
        console.print(f"[bold]Folder ID:[/bold] {share_info.folder_id}")
    console.print(f"[bold]下载目录:[/bold] {output_dir.resolve()}")
    console.print()

    aria2c_client: Aria2RpcClient | None = None
    if use_aria2c:
        if not shutil.which("aria2c"):
            console.print("[red]错误: --aria2c 需要系统已安装 aria2c，但未在 PATH 中找到。[/red]")
            console.print("[dim]安装方式: brew install aria2 (macOS) 或 apt install aria2 (Linux)[/dim]")
            raise SystemExit(1)
        aria2c_client = Aria2RpcClient(threads=threads)
        aria2c_client.start()
        console.print(f"[bold]aria2c:[/bold] 已启动 RPC 守护进程 (线程数: {threads})")

    api = CtfileAPI(share_info, password=password, delay=(delay_min, delay_max))
    api.page_url = url

    try:
        if share_info.link_type == "folder":
            _download_folder(api, output_dir, output_explicit, aria2c=aria2c_client)
        else:
            _download_single_file(api, share_info, output_dir, aria2c=aria2c_client)
    finally:
        if aria2c_client:
            aria2c_client.stop()
        api.close()


def _download_folder(api: CtfileAPI, output_dir: Path, output_explicit: bool = True, *, aria2c: Aria2RpcClient | None = None) -> None:
    """下载整个共享文件夹。"""
    console.print("[bold]正在扫描文件列表...[/bold]")
    file_tree = api.walk_folder()
    console.print(f"[green]找到 {len(file_tree)} 个文件[/green]")

    if not file_tree:
        console.print("[yellow]没有找到任何文件。[/yellow]")
        return

    table = Table(title="文件列表", show_lines=False)
    table.add_column("#", style="dim", width=5)
    table.add_column("路径", style="cyan")
    table.add_column("大小", style="green", width=12)
    for i, (path, entry) in enumerate(file_tree, 1):
        table.add_row(str(i), path, entry.size)
    console.print(table)
    console.print()

    # 未显式指定输出目录且根级条目 > 1 时，警告用户
    root_count = _count_root_items(file_tree)
    if not output_explicit and root_count > 1:
        console.print(
            f"[bold yellow]⚠ 该文件夹包含 {root_count} 个根目录项，"
            f"将直接下载到当前目录 ({output_dir})[/bold yellow]"
        )
        if not click.confirm("确定继续？"):
            console.print("[yellow]已取消。[/yellow]")
            return

    if not click.confirm(f"开始下载 {len(file_tree)} 个文件？"):
        console.print("[yellow]已取消。[/yellow]")
        return

    stats = batch_download(api, file_tree, output_dir, aria2c=aria2c)

    console.print()
    console.print("[bold]===== 下载完成 =====[/bold]")
    console.print(f"  [green]成功: {stats.success}[/green]")
    console.print(f"  [dim]跳过: {stats.skipped}[/dim]")
    console.print(f"  [red]失败: {stats.failed}[/red]")

    if stats.failed_files:
        console.print()
        console.print("[red]失败文件列表:[/red]")
        for f in stats.failed_files:
            console.print(f"  - {f}")


def _download_single_file(api: CtfileAPI, share_info, output_dir: Path, *, aria2c: Aria2RpcClient | None = None) -> None:
    """下载单个共享文件。"""
    console.print("[bold]正在获取文件信息...[/bold]")

    download_url, file_info = get_download_url_with_retry(api, share_info.share_code)
    if not download_url or not file_info:
        console.print("[red]获取下载链接失败[/red]")
        return

    file_name = file_info.get("file_name", "unknown")
    dest = output_dir / file_name
    if aria2c:
        success = download_file_aria2c(download_url, dest, aria2c)
    else:
        success = download_file(download_url, dest)

    if success:
        console.print(f"\n[green]下载完成: {dest}[/green]")
    else:
        console.print(f"\n[red]下载失败: {file_name}[/red]")


if __name__ == "__main__":
    cli()
