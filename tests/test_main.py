from ctfile_downloader.main import _count_root_items


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
