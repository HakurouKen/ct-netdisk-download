from unittest.mock import MagicMock, patch

from ctfile_downloader.api import CtfileAPIError, LinkExpiredError
from ctfile_downloader.downloader import batch_download, download_file_aria2c
from ctfile_downloader.parser import FileEntry


def _make_mock_api():
    api = MagicMock()
    api.get_file_info = MagicMock()
    api.get_download_url = MagicMock()
    return api


def test_batch_download_retries_on_expired_link(tmp_path):
    """When LinkExpiredError occurs, batch_download should refresh the code and retry."""
    api = _make_mock_api()
    entry = FileEntry(
        name="test.zip", code="tempdir-OLD", is_folder=False,
        parent_folder_id="123", parent_fk="abc",
    )
    file_tree = [("test.zip", entry)]

    # First get_file_info call raises LinkExpiredError (old code)
    # After refresh, second call succeeds (new code)
    def side_effect_file_info(code):
        if code == "tempdir-OLD":
            raise LinkExpiredError("文件链接已过期")
        return {
            "userid": 1, "file_id": 1, "file_chk": "chk",
            "file_name": "test.zip", "file_size": "10 MB",
            "verifycode": "v", "start_time": 0, "wait_seconds": 0,
        }
    api.get_file_info.side_effect = side_effect_file_info
    api.get_download_url.return_value = "https://cdn.example.com/test.zip"

    # Mock the folder refresh to return fresh entries
    api.get_folder_info.return_value = {"code": 200, "file": {"url": "/list"}}
    api.get_file_list.return_value = [
        FileEntry(name="test.zip", code="tempdir-NEW", is_folder=False),
    ]

    with patch("ctfile_downloader.downloader.download_file", return_value=True):
        stats = batch_download(api, file_tree, tmp_path)

    assert stats.success == 1
    assert stats.failed == 0
    assert entry.code == "tempdir-NEW"


def test_batch_download_refreshes_all_entries_in_same_folder(tmp_path):
    """When one file expires, all remaining entries from the same folder should be refreshed."""
    api = _make_mock_api()

    entries = [
        FileEntry(name=f"file{i}.zip", code=f"tempdir-OLD{i}", is_folder=False,
                  parent_folder_id="123", parent_fk="abc")
        for i in range(3)
    ]
    file_tree = [(f"file{i}.zip", entries[i]) for i in range(3)]

    # All old codes raise LinkExpiredError; new codes work
    expired_codes = {f"tempdir-OLD{i}" for i in range(3)}
    def side_effect_file_info(code):
        if code in expired_codes:
            raise LinkExpiredError("文件链接已过期")
        return {
            "userid": 1, "file_id": 1, "file_chk": "chk",
            "file_name": "test.zip", "file_size": "10 MB",
            "verifycode": "v", "start_time": 0, "wait_seconds": 0,
        }
    api.get_file_info.side_effect = side_effect_file_info
    api.get_download_url.return_value = "https://cdn.example.com/file.zip"

    # Mock folder refresh - returns fresh codes for all 3 files
    api.get_folder_info.return_value = {"code": 200, "file": {"url": "/list"}}
    api.get_file_list.return_value = [
        FileEntry(name=f"file{i}.zip", code=f"tempdir-NEW{i}", is_folder=False)
        for i in range(3)
    ]

    with patch("ctfile_downloader.downloader.download_file", return_value=True):
        stats = batch_download(api, file_tree, tmp_path)

    # All 3 should succeed after refresh
    assert stats.success == 3
    assert stats.failed == 0
    # Verify codes were updated
    for i in range(3):
        assert entries[i].code == f"tempdir-NEW{i}"


def test_batch_download_handles_refresh_failure(tmp_path):
    """When folder refresh fails, the file should be counted as failed and continue."""
    api = _make_mock_api()
    entry = FileEntry(
        name="test.zip", code="tempdir-OLD", is_folder=False,
        parent_folder_id="123", parent_fk="abc",
    )
    file_tree = [("test.zip", entry)]

    api.get_file_info.side_effect = LinkExpiredError("文件链接已过期")
    # Folder refresh fails
    api.get_folder_info.side_effect = CtfileAPIError("刷新文件夹失败")

    stats = batch_download(api, file_tree, tmp_path)

    assert stats.failed == 1
    assert stats.success == 0
    assert "test.zip" in stats.failed_files


def test_expired_link_refresh_does_not_trigger_rate_limit_pause(tmp_path):
    """Successful refresh + retry should reset consecutive_errors, not trigger rate-limit pauses."""
    api = _make_mock_api()

    entries = [
        FileEntry(name=f"file{i}.zip", code=f"tempdir-OLD{i}", is_folder=False,
                  parent_folder_id="123", parent_fk="abc")
        for i in range(5)
    ]
    file_tree = [(f"file{i}.zip", entries[i]) for i in range(5)]

    # All old codes expire, all new codes work
    expired_codes = {f"tempdir-OLD{i}" for i in range(5)}
    def side_effect_file_info(code):
        if code in expired_codes:
            raise LinkExpiredError("文件链接已过期")
        return {
            "userid": 1, "file_id": 1, "file_chk": "chk",
            "file_name": "test.zip", "file_size": "10 MB",
            "verifycode": "v", "start_time": 0, "wait_seconds": 0,
        }
    api.get_file_info.side_effect = side_effect_file_info
    api.get_download_url.return_value = "https://cdn.example.com/file.zip"
    api.get_folder_info.return_value = {"code": 200, "file": {"url": "/list"}}
    api.get_file_list.return_value = [
        FileEntry(name=f"file{i}.zip", code=f"tempdir-NEW{i}", is_folder=False)
        for i in range(5)
    ]

    import time
    with patch("ctfile_downloader.downloader.download_file", return_value=True), \
         patch.object(time, "sleep", wraps=time.sleep) as mock_sleep:
        stats = batch_download(api, file_tree, tmp_path)

    assert stats.success == 5
    # Verify we never called the long rate-limit sleep (30+ seconds)
    for call in mock_sleep.call_args_list:
        assert call[0][0] < 30, f"Unexpected long sleep: {call[0][0]}s — likely false rate-limit detection"


class TestDownloadFileAria2c:
    """测试 aria2c RPC 下载函数。"""

    def test_success_returns_true(self, tmp_path):
        """下载完成时返回 True。"""
        dest = tmp_path / "test.zip"
        mock_aria2c = MagicMock()
        mock_aria2c.add_uri.return_value = "gid-001"
        # 第一次轮询: active, 第二次: complete
        mock_aria2c.tell_status.side_effect = [
            {"status": "active", "totalLength": "1000", "completedLength": "500", "downloadSpeed": "100"},
            {"status": "complete", "totalLength": "1000", "completedLength": "1000", "downloadSpeed": "0"},
        ]

        result = download_file_aria2c("https://example.com/test.zip", dest, mock_aria2c)

        assert result is True
        mock_aria2c.add_uri.assert_called_once_with("https://example.com/test.zip", dest.parent, dest.name)

    def test_error_returns_false(self, tmp_path):
        """下载出错时返回 False。"""
        dest = tmp_path / "test.zip"
        mock_aria2c = MagicMock()
        mock_aria2c.add_uri.return_value = "gid-002"
        mock_aria2c.tell_status.return_value = {
            "status": "error", "totalLength": "0", "completedLength": "0",
            "downloadSpeed": "0", "errorCode": "1", "errorMessage": "network error",
        }

        result = download_file_aria2c("https://example.com/test.zip", dest, mock_aria2c)

        assert result is False

    def test_creates_parent_dirs(self, tmp_path):
        """下载前应创建父目录。"""
        dest = tmp_path / "sub" / "deep" / "test.zip"
        mock_aria2c = MagicMock()
        mock_aria2c.add_uri.return_value = "gid-003"
        mock_aria2c.tell_status.return_value = {
            "status": "complete", "totalLength": "100", "completedLength": "100", "downloadSpeed": "0",
        }

        download_file_aria2c("https://example.com/test.zip", dest, mock_aria2c)

        assert dest.parent.exists()

    def test_polls_until_complete(self, tmp_path):
        """应持续轮询直到下载完成。"""
        dest = tmp_path / "test.zip"
        mock_aria2c = MagicMock()
        mock_aria2c.add_uri.return_value = "gid-004"
        # 模拟 3 次 active 后 complete
        mock_aria2c.tell_status.side_effect = [
            {"status": "waiting", "totalLength": "0", "completedLength": "0", "downloadSpeed": "0"},
            {"status": "active", "totalLength": "1000", "completedLength": "200", "downloadSpeed": "100"},
            {"status": "active", "totalLength": "1000", "completedLength": "800", "downloadSpeed": "200"},
            {"status": "complete", "totalLength": "1000", "completedLength": "1000", "downloadSpeed": "0"},
        ]

        with patch("ctfile_downloader.downloader.time.sleep"):
            result = download_file_aria2c("https://example.com/test.zip", dest, mock_aria2c)

        assert result is True
        assert mock_aria2c.tell_status.call_count == 4
