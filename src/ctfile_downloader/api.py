# src/ctfile_downloader/api.py
from __future__ import annotations

import random
import time

import httpx

from ctfile_downloader.parser import FileEntry, ShareInfo, parse_file_list

API_BASE = "https://webapi.ctfile.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class CtfileAPIError(Exception):
    """城通网盘 API 错误"""


class CaptchaError(CtfileAPIError):
    """需要验证码"""


class CtfileAPI:
    def __init__(self, share_info: ShareInfo, delay: tuple[float, float] = (3.0, 8.0)):
        self.share_info = share_info
        self.delay = delay
        self.client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Origin": share_info.origin,
                "Referer": share_info.origin,
            },
            cookies={f"pass_d{share_info.folder_id}": share_info.password}
            if share_info.password and share_info.link_type == "folder"
            else {},
            timeout=30.0,
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        """请求间随机延迟，降低触发验证码概率。"""
        delay = random.uniform(*self.delay)
        time.sleep(delay)

    def get_folder_info(self, folder_id: str = "") -> dict:
        """获取文件夹信息，返回包含文件列表 URL 的 dict。"""
        self._throttle()
        params = {
            "path": "d",
            "d": self.share_info.share_code,
            "folder_id": folder_id,
            "passcode": self.share_info.password,
        }
        resp = self.client.get(f"{API_BASE}/getdir.php", params=params)
        resp.raise_for_status()
        data = resp.json()
        if "file" not in data:
            raise CtfileAPIError(f"获取文件夹信息失败: {data}")
        return data

    def get_file_list(self, list_url: str) -> list[FileEntry]:
        """获取文件列表并解析。"""
        self._throttle()
        url = f"{API_BASE}{list_url}" if list_url.startswith("/") else list_url
        resp = self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        aa_data = data.get("aaData", [])
        return parse_file_list(aa_data)

    def get_file_info(self, file_code: str) -> dict:
        """获取单个文件的元数据（userid, file_id, file_chk 等）。"""
        self._throttle()
        # Determine api path based on file code format
        parts = file_code.split("-")
        path = "f" if len(parts) >= 3 else "file"
        params = {
            "path": path,
            "f": file_code,
            "passcode": self.share_info.password,
            "token": "false",
            "r": str(random.random()),
            "ref": self.share_info.origin,
        }
        resp = self.client.get(f"{API_BASE}/getfile.php", params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 503:
            raise CtfileAPIError("文件已过期或被删除")
        if data.get("code") == 404:
            raise CtfileAPIError("文件不存在")
        if "file" not in data:
            raise CtfileAPIError(f"获取文件信息失败: {data}")
        return data["file"]

    def get_download_url(self, userid: int, file_id: int, file_chk: str) -> str:
        """获取免费用户下载链接。可能触发验证码。"""
        self._throttle()
        params = {
            "uid": str(userid),
            "fid": str(file_id),
            "file_chk": file_chk,
            "app": "0",
            "acheck": "2",
            "rd": str(random.random()),
        }
        resp = self.client.get(f"{API_BASE}/get_file_url.php", params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            raise CaptchaError(f"获取下载链接失败（可能需要验证码）: code={data.get('code')}")

        downurl = data.get("downurl", "")
        if not downurl:
            raise CaptchaError("返回空下载链接（可能需要验证码）")

        return downurl

    def walk_folder(self, folder_id: str = "", path: str = "") -> list[tuple[str, FileEntry]]:
        """递归遍历文件夹，返回 (相对路径, FileEntry) 列表。"""
        folder_info = self.get_folder_info(folder_id)
        list_url = folder_info["file"]["url"]
        entries = self.get_file_list(list_url)

        results: list[tuple[str, FileEntry]] = []
        for entry in entries:
            entry_path = f"{path}/{entry.name}" if path else entry.name
            if entry.is_folder:
                sub_results = self.walk_folder(entry.folder_id, entry_path)
                results.extend(sub_results)
            else:
                results.append((entry_path, entry))

        return results

    def close(self) -> None:
        self.client.close()
