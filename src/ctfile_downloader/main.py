from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ctfile_downloader.api import CtfileAPI
from ctfile_downloader.downloader import batch_download, download_file, get_download_url_with_retry
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
    default="downloads",
    help="下载目录（默认: downloads）",
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
def cli(url: str, password: str, output: str, delay_min: float, delay_max: float) -> None:
    """城通网盘通用下载器

    URL: 城通网盘共享链接（支持文件夹 /d/ 和单文件 /f/）
    """
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    share_info = parse_share_url(url)
    console.print(f"[bold]共享链接:[/bold] {url}")
    console.print(f"[bold]链接类型:[/bold] {'文件夹' if share_info.link_type == 'folder' else '单文件'}")
    console.print(f"[bold]Share Code:[/bold] {share_info.share_code}")
    if share_info.folder_id:
        console.print(f"[bold]Folder ID:[/bold] {share_info.folder_id}")
    console.print(f"[bold]下载目录:[/bold] {output_dir.resolve()}")
    console.print()

    api = CtfileAPI(share_info, password=password, delay=(delay_min, delay_max))
    api.page_url = url

    try:
        if share_info.link_type == "folder":
            _download_folder(api, output_dir)
        else:
            _download_single_file(api, share_info, output_dir)
    finally:
        api.close()


def _download_folder(api: CtfileAPI, output_dir: Path) -> None:
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

    if not click.confirm(f"开始下载 {len(file_tree)} 个文件？"):
        console.print("[yellow]已取消。[/yellow]")
        return

    stats = batch_download(api, file_tree, output_dir)

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


def _download_single_file(api: CtfileAPI, share_info, output_dir: Path) -> None:
    """下载单个共享文件。"""
    console.print("[bold]正在获取文件信息...[/bold]")

    download_url, file_info = get_download_url_with_retry(api, share_info.share_code)
    if not download_url or not file_info:
        console.print("[red]获取下载链接失败[/red]")
        return

    file_name = file_info.get("file_name", "unknown")
    dest = output_dir / file_name
    success = download_file(download_url, dest)

    if success:
        console.print(f"\n[green]下载完成: {dest}[/green]")
    else:
        console.print(f"\n[red]下载失败: {file_name}[/red]")


if __name__ == "__main__":
    cli()
