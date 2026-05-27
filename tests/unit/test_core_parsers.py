import pytest

from archive_indexer.core.parsers import BookmarkParser, extract_domain


def test_extract_domain_returns_netloc():
    assert extract_domain("https://example.com/path?q=1") == "example.com"


def test_bookmark_parser_extracts_title_url_and_folder():
    html = '<DL><DT><H3>Tech</H3><DL><DT><A HREF="https://example.com">Example</A></DL></DL>'
    parser = BookmarkParser()
    parser.feed(html)
    assert parser.items == [{"title": "Example", "url": "https://example.com", "folder": "Tech"}]
