from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import httpx


def _find_free_port() -> int:
    """找到一个可用的本地 TCP 端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Aria2RpcClient:
    """aria2c JSON-RPC 客户端，管理守护进程生命周期和 RPC 通信。"""

    def __init__(self, threads: int = 4) -> None:
        self.threads = threads
        port = _find_free_port()
        self.rpc_url = f"http://127.0.0.1:{port}/jsonrpc"
        self._port = port
        self._process: subprocess.Popen | None = None
        self._http = httpx.Client(timeout=10.0)

    def start(self) -> None:
        """启动 aria2c RPC 守护进程。"""
        cmd = [
            "aria2c",
            "--enable-rpc",
            f"--rpc-listen-port={self._port}",
            "--rpc-listen-all=false",
            "--console-log-level=error",
        ]
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._wait_for_rpc()

    def _wait_for_rpc(self, timeout: float = 5.0) -> None:
        """等待 RPC 服务就绪。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._call("aria2.getVersion")
                return
            except (httpx.ConnectError, httpx.ReadError, OSError):
                time.sleep(0.1)
        raise RuntimeError("aria2c RPC 启动超时")

    def stop(self) -> None:
        """关闭 aria2c 进程。"""
        try:
            self._call("aria2.shutdown")
        except Exception:
            pass
        if self._process:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
        self._http.close()

    def _call(self, method: str, params: list | None = None):
        """发送 JSON-RPC 请求并返回 result。"""
        payload = {
            "jsonrpc": "2.0",
            "id": "ctdl",
            "method": method,
            "params": params or [],
        }
        resp = self._http.post(self.rpc_url, json=payload)
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"aria2c RPC 错误: {data['error']}")
        return data["result"]

    def add_uri(self, url: str, directory: Path, filename: str) -> str:
        """添加下载任务，返回 GID。"""
        options = {
            "dir": str(directory),
            "out": filename,
            "split": str(self.threads),
            "max-connection-per-server": str(self.threads),
            "continue": "true",
            "auto-file-renaming": "false",
            "allow-overwrite": "true",
        }
        return self._call("aria2.addUri", [[url], options])

    def tell_status(self, gid: str) -> dict:
        """查询下载状态。"""
        keys = [
            "status", "totalLength", "completedLength",
            "downloadSpeed", "errorCode", "errorMessage",
        ]
        return self._call("aria2.tellStatus", [gid, keys])

    def __enter__(self) -> Aria2RpcClient:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
