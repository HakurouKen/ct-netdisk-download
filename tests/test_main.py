from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from ctfile_downloader.main import _count_root_items, cli


def test_count_root_items_single_file():
    """单个根文件应返回 1。"""
    file_tree = [("readme.txt", None)]
    assert _count_root_items(file_tree) == 1


def test_count_root_items_single_folder():
    """单个文件夹下的多个文件应返回 1。"""
    file_tree = [
        ("docs/a.txt", None),
        ("docs/b.txt", None),
        ("docs/sub/c.txt", None),
    ]
    assert _count_root_items(file_tree) == 1


def test_count_root_items_multiple():
    """混合根级文件和文件夹应正确计数。"""
    file_tree = [
        ("readme.txt", None),
        ("docs/a.txt", None),
        ("src/main.py", None),
    ]
    assert _count_root_items(file_tree) == 3


def test_count_root_items_empty():
    """空列表应返回 0。"""
    assert _count_root_items([]) == 0


def test_default_output_is_cwd(tmp_path, monkeypatch):
    """未指定 -o 时，默认下载到当前目录。"""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main._download_single_file") as mock_dl:

        mock_info = MagicMock()
        mock_info.link_type = "file"
        mock_info.share_code = "abc"
        mock_info.folder_id = None
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        result = runner.invoke(cli, ["https://url.cn/f/abc"])

    # _download_single_file 应该接收到当前目录（resolve 后等于 tmp_path）
    called_output_dir = mock_dl.call_args[0][2]
    assert called_output_dir == tmp_path


def test_explicit_output_is_respected(tmp_path):
    """显式指定 -o 时应使用指定路径。"""
    target = tmp_path / "my_downloads"

    runner = CliRunner()
    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main._download_single_file") as mock_dl:

        mock_info = MagicMock()
        mock_info.link_type = "file"
        mock_info.share_code = "abc"
        mock_info.folder_id = None
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        result = runner.invoke(cli, ["https://url.cn/f/abc", "-o", str(target)])

    called_output_dir = mock_dl.call_args[0][2]
    assert called_output_dir == target.resolve()
