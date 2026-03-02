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
    def __init__(self, share_info: ShareInfo, password: str = "", delay: tuple[float, float] = (3.0, 8.0)):
        self.share_info = share_info
        self.password = password
        self.delay = delay
        self.page_url = ""  # set later for ref param

        cookies = {}
        if password and share_info.link_type == "folder":
            cookies[f"pass_d{share_info.folder_id}"] = password

        self.client = httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Origin": share_info.origin,
                "Referer": share_info.origin + "/",
            },
            cookies=cookies,
            timeout=30.0,
            follow_redirects=True,
        )

    def _throttle(self) -> None:
        delay = random.uniform(*self.delay)
        time.sleep(delay)

    def get_folder_info(self, folder_id: str = "", fk: str = "") -> dict:
        """获取文件夹信息。"""
        self._throttle()
        if not folder_id:
            folder_id = self.share_info.folder_id
        if not fk:
            fk = self.share_info.fk

        params = {
            "path": "d",
            "d": self.share_info.share_code,
            "folder_id": folder_id,
            "fk": fk,
            "passcode": self.password,
            "r": str(random.random()),
            "ref": "",
            "url": self.page_url,
        }
        resp = self.client.get(f"{API_BASE}/getdir.php", params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 423:
            msg = data.get("file", {}).get("message", "需要密码")
            raise CtfileAPIError(f"密码验证失败: {msg}")
        if "file" not in data or not data["file"].get("url"):
            raise CtfileAPIError(f"获取文件夹信息失败: {data}")
        return data

    def get_file_list(self, list_url: str) -> list[FileEntry]:
        """获取并解析文件列表。"""
        self._throttle()
        url = f"{API_BASE}{list_url}" if list_url.startswith("/") else list_url
        resp = self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        aa_data = data.get("aaData", [])
        return parse_file_list(aa_data)

    def get_file_info(self, file_code: str) -> dict:
        """获取文件元数据。file_code 可以是 tempdir-XXX 或传统格式。"""
        self._throttle()
        params = {
            "path": "f",
            "f": file_code,
            "passcode": self.password,
            "r": str(random.random()),
            "ref": "",
            "url": self.page_url,
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

    def get_download_url(self, file_info: dict) -> str:
        """获取下载链接。使用 getfile 返回的 verifycode。"""
        self._throttle()
        params = {
            "uid": str(file_info["userid"]),
            "fid": str(file_info["file_id"]),
            "folder_id": "0",
            "file_chk": file_info["file_chk"],
            "start_time": str(file_info.get("start_time", 0)),
            "wait_seconds": str(file_info.get("wait_seconds", 0)),
            "mb": "0",
            "app": "0",
            "acheck": "1",
            "verifycode": file_info.get("verifycode", ""),
            "rd": str(random.random()),
        }
        resp = self.client.get(f"{API_BASE}/get_file_url.php", params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            raise CaptchaError(f"获取下载链接失败: code={data.get('code')}")

        downurl = data.get("downurl", "")
        if not downurl:
            raise CaptchaError("返回空下载链接")

        return downurl

    def walk_folder(self, folder_id: str = "", fk: str = "", path: str = "") -> list[tuple[str, FileEntry]]:
        """递归遍历文件夹。"""
        folder_info = self.get_folder_info(folder_id, fk)
        list_url = folder_info["file"]["url"]
        entries = self.get_file_list(list_url)

        results: list[tuple[str, FileEntry]] = []
        for entry in entries:
            entry_path = f"{path}/{entry.name}" if path else entry.name
            if entry.is_folder:
                sub_results = self.walk_folder(entry.folder_id, entry.fk, entry_path)
                results.extend(sub_results)
            else:
                results.append((entry_path, entry))

        return results

    def close(self) -> None:
        self.client.close()
