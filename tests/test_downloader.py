from unittest.mock import MagicMock, patch
from pathlib import Path

from ctfile_downloader.api import LinkExpiredError, CtfileAPIError
from ctfile_downloader.downloader import batch_download
from ctfile_downloader.parser import FileEntry


def _make_mock_api():
    api = MagicMock()
    api.get_file_info = MagicMock()
    api.get_download_url = MagicMock()
    api.refresh_file_code = MagicMock()
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
