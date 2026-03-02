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
    fk: str = ""  # folder key from URL
    api_path: str = ""  # "f" or "file", only for single file links


@dataclass
class FileEntry:
    name: str
    code: str  # tempdir-XXX for files, empty for folders
    is_folder: bool
    folder_id: str = ""
    fk: str = ""  # folder key for subfolders
    size: str = ""  # file size string e.g. "3.60 MB"
    parent_folder_id: str = ""  # folder this file belongs to
    parent_fk: str = ""  # folder key of parent folder


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
        password = qs.get("fk", qs.get("p", [""]))[0]  # fk might be folder key, not password
        fk = qs.get("fk", [""])[0]
        return ShareInfo(
            share_code=share_code,
            folder_id=folder_id,
            password="",  # password is provided separately via CLI
            origin=origin,
            link_type="folder",
            fk=fk,
        )
    else:
        password = qs.get("p", [""])[0]
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
        size = row[2].strip() if len(row) > 2 else ""

        # 子文件夹: load_subdir(ID, 'FK')
        subdir_match = re.search(r"load_subdir\((\d+),\s*['\"]([^'\"]+)['\"]\)", html)
        if subdir_match:
            folder_id = subdir_match.group(1)
            fk = subdir_match.group(2)
            name_match = re.search(r">([^<]+)</a>", html)
            name = name_match.group(1).strip() if name_match else "unknown_folder"
            entries.append(FileEntry(name=name, code="", is_folder=True, folder_id=folder_id, fk=fk))
            continue

        # 文件: href="#/f/tempdir-XXX" or href="/f/CODE"
        tempdir_match = re.search(r'href="[^"]*?#/f/(tempdir-[^"]+)"', html)
        if tempdir_match:
            code = tempdir_match.group(1)
            name_match = re.search(r">([^<]+)</a>", html)
            name = name_match.group(1).strip() if name_match else "unknown_file"
            entries.append(FileEntry(name=name, code=code, is_folder=False, size=size))
            continue

        # Legacy format: href="/f/CODE"
        file_match = re.search(r'href="[^"]*?/f/([^"]+)"', html)
        name_match = re.search(r">([^<]+)</a>", html)
        if file_match and name_match:
            code = file_match.group(1)
            name = name_match.group(1).strip()
            entries.append(FileEntry(name=name, code=code, is_folder=False, size=size))

    return entries
