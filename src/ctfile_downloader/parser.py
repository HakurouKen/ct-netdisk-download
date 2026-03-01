from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass
class ShareInfo:
    share_code: str
    folder_id: str
    password: str
    origin: str
    link_type: str  # "folder" or "file"
    api_path: str = ""  # "f" (new 3-part) or "file" (old 2-part), only for file links


@dataclass
class FileEntry:
    name: str
    code: str
    is_folder: bool
    folder_id: str = ""


def parse_share_url(url: str) -> ShareInfo:
    """解析城通网盘共享链接。支持文件夹 (/d/) 和单文件 (/f/) 链接。"""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.hostname}"
    qs = parse_qs(parsed.query)

    path_parts = parsed.path.strip("/").split("/")
    link_prefix = path_parts[0] if path_parts else ""
    share_code = path_parts[1] if len(path_parts) >= 2 else ""

    if link_prefix == "d":
        folder_id = qs.get("d", [""])[0]
        password = qs.get("fk", [""])[0]
        return ShareInfo(
            share_code=share_code,
            folder_id=folder_id,
            password=password,
            origin=origin,
            link_type="folder",
        )
    else:
        # /f/ single file link
        password = qs.get("p", [""])[0]
        # 3-part code = new format (path=f), 2-part = old format (path=file)
        parts = share_code.split("-")
        api_path = "f" if len(parts) >= 3 else "file"
        return ShareInfo(
            share_code=share_code,
            folder_id="",
            password=password,
            origin=origin,
            link_type="file",
            api_path=api_path,
        )


def parse_file_list(aa_data: list[list[str]]) -> list[FileEntry]:
    """解析 aaData HTML 片段，提取文件/文件夹条目。"""
    entries: list[FileEntry] = []

    for row in aa_data:
        if len(row) < 2:
            continue

        html = row[1]

        # 子文件夹：含 load_subdir()
        subdir_match = re.search(r"load_subdir\(['\"](\d+)['\"]\)", html)
        if subdir_match:
            folder_id = subdir_match.group(1)
            name_match = re.search(r">([^<]+)</a>", html)
            name = name_match.group(1).strip() if name_match else "unknown_folder"
            entries.append(FileEntry(name=name, code="", is_folder=True, folder_id=folder_id))
            continue

        # 普通文件
        file_match = re.search(r'href="[^"]*?/f/([^"]+)"', html)
        name_match = re.search(r">([^<]+)</a>", html)

        if file_match and name_match:
            code = file_match.group(1)
            name = name_match.group(1).strip()
            entries.append(FileEntry(name=name, code=code, is_folder=False))

    return entries
