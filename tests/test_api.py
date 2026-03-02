import pytest
from unittest.mock import MagicMock

from ctfile_downloader.api import CtfileAPIError, CtfileAPI, LinkExpiredError
from ctfile_downloader.parser import FileEntry, ShareInfo


def test_link_expired_error_is_ctfile_api_error():
    """LinkExpiredError should be a subclass of CtfileAPIError."""
    assert issubclass(LinkExpiredError, CtfileAPIError)


def test_link_expired_error_message():
    err = LinkExpiredError("文件链接已过期")
    assert "过期" in str(err)


def _make_api():
    """Create a CtfileAPI with mocked client for testing."""
    share_info = ShareInfo(
        share_code="test", folder_id="123", password="",
        origin="https://test.ctfile.com", link_type="folder", fk="abc",
    )
    api = CtfileAPI(share_info, delay=(0, 0))
    return api


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.headers = {}
    return resp


def test_get_file_info_raises_link_expired_on_timeout_message():
    """404 with '超时' message should raise LinkExpiredError, not CtfileAPIError."""
    api = _make_api()
    api.client = MagicMock()
    api.client.get.return_value = _mock_response({
        "code": 404,
        "file": {"code": 404, "message": "下载链接已超时，请重新从文件夹获取。"},
    })

    with pytest.raises(LinkExpiredError, match="过期"):
        api.get_file_info("tempdir-EXPIRED")


def test_get_file_info_raises_ctfile_error_on_plain_404():
    """404 without '超时' message should still raise CtfileAPIError."""
    api = _make_api()
    api.client = MagicMock()
    api.client.get.return_value = _mock_response({
        "code": 404,
        "file": {"code": 404, "message": "文件不存在"},
    })

    with pytest.raises(CtfileAPIError, match="文件不存在"):
        api.get_file_info("tempdir-NOTFOUND")
    # Ensure it's NOT a LinkExpiredError
    try:
        api.get_file_info("tempdir-NOTFOUND")
    except LinkExpiredError:
        pytest.fail("Should not raise LinkExpiredError for plain 404")
    except CtfileAPIError:
        pass  # expected


def test_refresh_file_code_finds_matching_file():
    """refresh_file_code should return the new code for a matching file name."""
    api = _make_api()
    api.client = MagicMock()

    # Mock get_folder_info
    api.client.get.side_effect = [
        # First call: get_folder_info
        _mock_response({"code": 200, "file": {"url": "/mock_list_url"}}),
        # Second call: get_file_list
        _mock_response({
            "aaData": [
                ["", '<a target="_blank" href="#/f/tempdir-NEWCODE">test.zip</a>', "10 MB", ""],
                ["", '<a target="_blank" href="#/f/tempdir-OTHER">other.zip</a>', "5 MB", ""],
            ]
        }),
    ]

    entry = FileEntry(
        name="test.zip", code="tempdir-OLDCODE", is_folder=False,
        parent_folder_id="999", parent_fk="xyz",
    )
    new_code = api.refresh_file_code(entry)
    assert new_code == "tempdir-NEWCODE"


def test_refresh_file_code_returns_none_when_not_found():
    """refresh_file_code should return None if the file is no longer in the folder."""
    api = _make_api()
    api.client = MagicMock()

    api.client.get.side_effect = [
        _mock_response({"code": 200, "file": {"url": "/mock_list_url"}}),
        _mock_response({"aaData": [
            ["", '<a target="_blank" href="#/f/tempdir-OTHER">other.zip</a>', "5 MB", ""],
        ]}),
    ]

    entry = FileEntry(
        name="missing.zip", code="tempdir-GONE", is_folder=False,
        parent_folder_id="999", parent_fk="xyz",
    )
    assert api.refresh_file_code(entry) is None
