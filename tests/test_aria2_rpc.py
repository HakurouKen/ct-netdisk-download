from pathlib import Path
from unittest.mock import MagicMock, patch

from ctfile_downloader.aria2_rpc import Aria2RpcClient


def _mock_rpc_response(result):
    """创建 JSON-RPC 成功响应的 mock。"""
    resp = MagicMock()
    resp.json.return_value = {"jsonrpc": "2.0", "id": "ctdl", "result": result}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_rpc_error(code, message):
    """创建 JSON-RPC 错误响应的 mock。"""
    resp = MagicMock()
    resp.json.return_value = {
        "jsonrpc": "2.0", "id": "ctdl",
        "error": {"code": code, "message": message},
    }
    resp.raise_for_status = MagicMock()
    return resp


class TestAria2RpcClientRpc:
    """测试 JSON-RPC 通信（不启动真实进程）。"""

    def test_add_uri_sends_correct_params(self):
        client = Aria2RpcClient.__new__(Aria2RpcClient)
        client.threads = 4
        client.rpc_url = "http://127.0.0.1:16800/jsonrpc"
        client._http = MagicMock()
        client._http.post.return_value = _mock_rpc_response("abc123")

        gid = client.add_uri("https://example.com/file.zip", Path("/tmp"), "file.zip")

        assert gid == "abc123"
        payload = client._http.post.call_args[1]["json"]
        assert payload["method"] == "aria2.addUri"
        # params: [[url], {options}]
        uris, options = payload["params"]
        assert uris == ["https://example.com/file.zip"]
        assert options["dir"] == "/tmp"
        assert options["out"] == "file.zip"
        assert options["split"] == "4"
        assert options["max-connection-per-server"] == "4"

    def test_tell_status_returns_status_dict(self):
        client = Aria2RpcClient.__new__(Aria2RpcClient)
        client.rpc_url = "http://127.0.0.1:16800/jsonrpc"
        client._http = MagicMock()
        status_data = {
            "status": "active",
            "totalLength": "1000000",
            "completedLength": "500000",
            "downloadSpeed": "100000",
        }
        client._http.post.return_value = _mock_rpc_response(status_data)

        result = client.tell_status("abc123")

        assert result["status"] == "active"
        assert result["completedLength"] == "500000"
        payload = client._http.post.call_args[1]["json"]
        assert payload["method"] == "aria2.tellStatus"
        assert payload["params"][0] == "abc123"

    def test_rpc_error_raises_runtime_error(self):
        client = Aria2RpcClient.__new__(Aria2RpcClient)
        client.rpc_url = "http://127.0.0.1:16800/jsonrpc"
        client._http = MagicMock()
        client._http.post.return_value = _mock_rpc_error(1, "Unknown GID")

        import pytest
        with pytest.raises(RuntimeError, match="aria2c RPC 错误"):
            client.tell_status("bad-gid")


class TestAria2RpcClientLifecycle:
    """测试进程生命周期管理。"""

    def test_start_launches_aria2c_with_rpc_flags(self):
        with patch("ctfile_downloader.aria2_rpc.subprocess.Popen") as mock_popen, \
             patch.object(Aria2RpcClient, "_wait_for_rpc"):
            client = Aria2RpcClient(threads=4)
            client.start()

        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "aria2c"
        assert "--enable-rpc" in cmd
        assert any("--rpc-listen-port=" in arg for arg in cmd)

    def test_stop_sends_shutdown_and_waits(self):
        client = Aria2RpcClient.__new__(Aria2RpcClient)
        client._process = MagicMock()
        client._http = MagicMock()
        client._http.post.return_value = _mock_rpc_response("OK")
        client.rpc_url = "http://127.0.0.1:16800/jsonrpc"

        client.stop()

        # 应发送 aria2.shutdown RPC
        payload = client._http.post.call_args[1]["json"]
        assert payload["method"] == "aria2.shutdown"
        # 应等待进程退出
        client._process.wait.assert_called_once()
        # 应关闭 HTTP client
        client._http.close.assert_called_once()

    def test_context_manager_starts_and_stops(self):
        with patch.object(Aria2RpcClient, "start") as mock_start, \
             patch.object(Aria2RpcClient, "stop") as mock_stop:
            with Aria2RpcClient(threads=4) as client:
                pass

        mock_start.assert_called_once()
        mock_stop.assert_called_once()
