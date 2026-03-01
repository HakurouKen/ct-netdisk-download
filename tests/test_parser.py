# tests/test_parser.py
from ctfile_downloader.parser import parse_share_url, FileEntry, parse_file_list


def test_parse_folder_url():
    url = "https://url01.ctfile.com/d/11449240-33792850-725200?d=33792850&fk=387c4e"
    result = parse_share_url(url)
    assert result.share_code == "11449240-33792850-725200"
    assert result.folder_id == "33792850"
    assert result.password == "387c4e"
    assert result.origin == "https://url01.ctfile.com"
    assert result.link_type == "folder"


def test_parse_folder_url_no_password():
    url = "https://url66.ctfile.com/d/12345-67890-abcdef?d=67890"
    result = parse_share_url(url)
    assert result.share_code == "12345-67890-abcdef"
    assert result.folder_id == "67890"
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


def test_parse_file_list_files():
    aa_data = [
        [
            '<div class="file_item"><img src="icon.png"></div>',
            '<a href="/f/12345-67890" class="fileName">test_file.zip</a>',
            "50MB",
            "2024-01-01",
        ],
        [
            '<div class="file_item"><img src="icon.png"></div>',
            '<a href="/f/12345-11111" class="fileName">readme.txt</a>',
            "1KB",
            "2024-01-02",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 2
    assert entries[0].name == "test_file.zip"
    assert entries[0].code == "12345-67890"
    assert entries[0].is_folder is False
    assert entries[1].name == "readme.txt"
    assert entries[1].code == "12345-11111"


def test_parse_file_list_folders():
    aa_data = [
        [
            '<div class="file_item"><img src="folder.png"></div>',
            '<a href="javascript:void(0)" onclick="load_subdir(\'99999\')">子文件夹A</a>',
            "-",
            "2024-01-01",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 1
    assert entries[0].name == "子文件夹A"
    assert entries[0].is_folder is True
    assert entries[0].folder_id == "99999"


def test_parse_file_list_mixed():
    aa_data = [
        [
            "",
            '<a href="javascript:void(0)" onclick="load_subdir(\'111\')">folder1</a>',
            "-",
            "",
        ],
        [
            "",
            '<a href="/f/abc-def" class="fileName">file1.bin</a>',
            "10MB",
            "",
        ],
    ]
    entries = parse_file_list(aa_data)
    assert len(entries) == 2
    assert entries[0].is_folder is True
    assert entries[0].folder_id == "111"
    assert entries[1].is_folder is False
    assert entries[1].code == "abc-def"
