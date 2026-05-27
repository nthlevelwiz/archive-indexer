from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    return urlparse(url).netloc


class BookmarkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_folder: list[str] = []
        self.items: list[dict[str, str]] = []
        self._last_title = ""
        self._in_h3 = False
        self._current_href: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "h3":
            self._in_h3 = True
        if tag.lower() == "a":
            self._current_href = attrs.get("href")

    def handle_data(self, data):
        if self._in_h3:
            self._last_title = data.strip()
        elif self._current_href:
            title = data.strip()
            if title:
                self.items.append(
                    {"title": title, "url": self._current_href, "folder": "/".join(self.current_folder)}
                )

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "h3":
            self._in_h3 = False
            if self._last_title:
                self.current_folder.append(self._last_title)
        elif t == "dl" and self.current_folder:
            self.current_folder.pop()
        elif t == "a":
            self._current_href = None
