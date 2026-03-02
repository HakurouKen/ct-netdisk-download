from ctfile_downloader.parser import parse_share_url, FileEntry, parse_file_list


def test_parse_folder_url():
    url = "https://url01.ctfile.com/d/11449240-33792850-725200?d=33792850&fk=387c4e"
    result = parse_share_url(url)
    assert result.share_code == "11449240-33792850-725200"
    assert result.folder_id == "33792850"
    assert result.fk == "387c4e"
    assert result.password == ""  # password is separate from fk
    assert result.origin == "https://url01.ctfile.com"
    assert result.link_type == "folder"


def test_parse_folder_url_no_fk():
    url = "https://url66.ctfile.com/d/12345-67890-abcdef?d=67890"
    result = parse_share_url(url)
    assert result.share_code == "12345-67890-abcdef"
    assert result.folder_id == "67890"
    assert result.fk == ""
    assert result.password == ""
    assert result.origin == "https://url66.ctfile.com"
    assert result.link_type == "folder"


def test_parse_single_file_url_new_format():
    url = "https://url01.ctfile.com/f/12345-67890-abcdef?p=secretpass"
    result = parse_share_url(url)
    assert result.share_code == "12345-67890-abcdef"
    assert result.password == "secretpass"
    assert result.origin == "https://url01.ctfile.com"
    assert result.link_type == "file"
    assert result.api_path == "f"


def test_parse_single_file_url_old_format():
    url = "https://url01.ctfile.com/f/12345-67890?p=pass"
    result = parse_share_url(url)
    assert result.share_code == "12345-67890"
    assert result.password == "pass"
    assert result.link_type == "file"
    assert result.api_path == "file"


def test_parse_file_list_tempdir_files():
    """测试解析 tempdir 格式的文件链接"""
    aa_data = [
        [
            '<div class="custom-control"></div>',
            '<div class="filename-cell"><div class="file-icon"><img src="zip.svg" alt="zip"></div><div class="filename-text"><a target="_blank" href="#/f/tempdir-AGBWYFNlDWFTaFE0BDFcPlV6V2VTZVxpWzZWNFU2ADoH">0499 - test_file.zip</a></div></div>',
            "3.60 MB",
            "2024-01-01",
        ],
        [
            '<div class="custom-control"></div>',
            '<div class="filename-cell"><div class="file-icon"><img src="txt.svg" alt="txt"></div><div class="filename-text"><a target="_blank" href="#/f/tempdir-C2sHMV1rXzMGPQVgATRVNw8g">readme.txt</a></div></div>',
            "1 KB",
            "2024-01-02",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 2
    assert entries[0].name == "0499 - test_file.zip"
    assert entries[0].code == "tempdir-AGBWYFNlDWFTaFE0BDFcPlV6V2VTZVxpWzZWNFU2ADoH"
    assert entries[0].is_folder is False
    assert entries[0].size == "3.60 MB"
    assert entries[1].name == "readme.txt"
    assert entries[1].code == "tempdir-C2sHMV1rXzMGPQVgATRVNw8g"


def test_parse_file_list_folders_with_fk():
    """测试解析带 fk 参数的子文件夹"""
    aa_data = [
        [
            '<div class="custom-control"></div>',
            '<div class="filename-cell"><div class="file-icon"><img src="folder.svg" alt="folder"></div><div class="filename-text"><a href="javascript:void(0)" onclick="load_subdir(33792853, \'b05744\')">0001-0500</a></div></div>',
            "- -",
            "2024-01-01",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 1
    assert entries[0].name == "0001-0500"
    assert entries[0].is_folder is True
    assert entries[0].folder_id == "33792853"
    assert entries[0].fk == "b05744"


def test_parse_file_list_mixed():
    aa_data = [
        [
            "",
            '<a href="javascript:void(0)" onclick="load_subdir(111, \'abc123\')">folder1</a>',
            "- -",
            "",
        ],
        [
            "",
            '<a target="_blank" href="#/f/tempdir-ABCDEF123456">file1.bin</a>',
            "10 MB",
            "",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 2
    assert entries[0].is_folder is True
    assert entries[0].folder_id == "111"
    assert entries[0].fk == "abc123"
    assert entries[1].is_folder is False
    assert entries[1].code == "tempdir-ABCDEF123456"
    assert entries[1].size == "10 MB"
