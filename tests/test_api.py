import pytest
from unittest.mock import MagicMock

from ctfile_downloader.api import CtfileAPIError, CtfileAPI, LinkExpiredError
from ctfile_downloader.parser import ShareInfo


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
