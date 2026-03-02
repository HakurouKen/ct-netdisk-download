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


def test_folder_multi_root_prompts_confirmation(tmp_path, monkeypatch):
    """文件夹有多个根项且未指定 -o 时，应额外提示确认。"""
    monkeypatch.chdir(tmp_path)
    from ctfile_downloader.parser import FileEntry

    runner = CliRunner()
    fake_tree = [
        ("file1.txt", FileEntry(name="file1.txt", code="t1", is_folder=False)),
        ("dir1/file2.txt", FileEntry(name="file2.txt", code="t2", is_folder=False)),
    ]

    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main.batch_download") as mock_batch:

        mock_info = MagicMock()
        mock_info.link_type = "folder"
        mock_info.share_code = "abc"
        mock_info.folder_id = "123"
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api.walk_folder.return_value = fake_tree
        mock_api_cls.return_value = mock_api

        # 用户在第一个确认（多根项警告）处回答 "n"
        result = runner.invoke(cli, ["https://url.cn/d/abc"], input="n\n")

    # 应该看到多根项警告文字
    assert "根目录项" in result.output
    # batch_download 不应该被调用（用户取消了）
    mock_batch.assert_not_called()


def test_folder_single_root_no_extra_prompt(tmp_path, monkeypatch):
    """文件夹只有 1 个根项时，不应出现额外确认。"""
    monkeypatch.chdir(tmp_path)
    from ctfile_downloader.parser import FileEntry

    runner = CliRunner()
    fake_tree = [
        ("docs/a.txt", FileEntry(name="a.txt", code="t1", is_folder=False)),
        ("docs/b.txt", FileEntry(name="b.txt", code="t2", is_folder=False)),
    ]

    mock_stats = MagicMock()
    mock_stats.success = 2
    mock_stats.failed = 0
    mock_stats.skipped = 0
    mock_stats.failed_files = []

    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main.batch_download", return_value=mock_stats) as mock_batch:

        mock_info = MagicMock()
        mock_info.link_type = "folder"
        mock_info.share_code = "abc"
        mock_info.folder_id = "123"
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api.walk_folder.return_value = fake_tree
        mock_api_cls.return_value = mock_api

        # 只需要回答一次 "y"（标准的"开始下载？"确认）
        result = runner.invoke(cli, ["https://url.cn/d/abc"], input="y\n")

    # 不应出现多根项警告
    assert "根目录项" not in result.output
    # batch_download 应该被调用
    mock_batch.assert_called_once()


def test_folder_multi_root_skipped_with_explicit_output(tmp_path):
    """显式指定 -o 时，即使多根项也不应出现额外确认。"""
    from ctfile_downloader.parser import FileEntry

    runner = CliRunner()
    fake_tree = [
        ("file1.txt", FileEntry(name="file1.txt", code="t1", is_folder=False)),
        ("file2.txt", FileEntry(name="file2.txt", code="t2", is_folder=False)),
    ]

    mock_stats = MagicMock()
    mock_stats.success = 2
    mock_stats.failed = 0
    mock_stats.skipped = 0
    mock_stats.failed_files = []

    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main.batch_download", return_value=mock_stats) as mock_batch:

        mock_info = MagicMock()
        mock_info.link_type = "folder"
        mock_info.share_code = "abc"
        mock_info.folder_id = "123"
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api.walk_folder.return_value = fake_tree
        mock_api_cls.return_value = mock_api

        # 只需要回答标准确认 "y"
        result = runner.invoke(cli, ["https://url.cn/d/abc", "-o", str(tmp_path)], input="y\n")

    mock_batch.assert_called_once()


def test_aria2c_flag_passed_to_single_file(tmp_path, monkeypatch):
    """--aria2c 标志应透传到 _download_single_file。"""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main._download_single_file") as mock_dl, \
         patch("ctfile_downloader.main.Aria2RpcClient") as mock_rpc_cls, \
         patch("ctfile_downloader.main.shutil.which", return_value="/usr/bin/aria2c"):

        mock_info = MagicMock()
        mock_info.link_type = "file"
        mock_info.share_code = "abc"
        mock_info.folder_id = None
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_rpc = MagicMock()
        mock_rpc_cls.return_value = mock_rpc

        result = runner.invoke(cli, ["https://url.cn/f/abc", "--aria2c"])

    # _download_single_file 应通过 keyword arg 接收 aria2c 客户端
    call_kwargs = mock_dl.call_args[1]
    assert call_kwargs["aria2c"] is mock_rpc


def test_aria2c_threads_override(tmp_path, monkeypatch):
    """--threads 应传递给 Aria2RpcClient。"""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    with patch("ctfile_downloader.main.parse_share_url") as mock_parse, \
         patch("ctfile_downloader.main.CtfileAPI") as mock_api_cls, \
         patch("ctfile_downloader.main._download_single_file"), \
         patch("ctfile_downloader.main.Aria2RpcClient") as mock_rpc_cls, \
         patch("ctfile_downloader.main.shutil.which", return_value="/usr/bin/aria2c"):

        mock_info = MagicMock()
        mock_info.link_type = "file"
        mock_info.share_code = "abc"
        mock_info.folder_id = None
        mock_parse.return_value = mock_info

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_rpc = MagicMock()
        mock_rpc_cls.return_value = mock_rpc

        result = runner.invoke(cli, ["https://url.cn/f/abc", "--aria2c", "--threads", "8"])

    # Aria2RpcClient 应以 threads=8 初始化
    mock_rpc_cls.assert_called_once_with(threads=8)


def test_no_aria2c_passes_none(tmp_path, monkeypatch):
    """不使用 --aria2c 时，aria2c 应为 None。"""
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

    call_kwargs = mock_dl.call_args[1]
    assert call_kwargs["aria2c"] is None


def test_aria2c_not_installed_exits_with_error(tmp_path, monkeypatch):
    """--aria2c 但 aria2c 未安装时应报错退出。"""
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    with patch("ctfile_downloader.main.shutil.which", return_value=None):
        result = runner.invoke(cli, ["https://url.cn/f/abc", "--aria2c"])

    assert result.exit_code != 0
    assert "aria2c" in result.output
