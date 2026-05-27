from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    return urlparse(url).netloc
    
def mini_yaml_parse(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    current_list = None
    current_item = None
    for ln in lines:
        if not ln.startswith(" ") and ln.endswith(":"):
            key = ln[:-1]
            result[key] = []
            current_list = result[key]
            current_item = None
        elif ln.strip().startswith("- "):
            current_item = {}
            assert isinstance(current_list, list)
            current_list.append(current_item)
            rest = ln.strip()[2:]
            if ":" in rest:
                k, v = rest.split(":", 1)
                current_item[k.strip()] = v.strip()
        elif ":" in ln and current_item is not None:
            k, v = ln.strip().split(":", 1)
            vv = v.strip()
            current_item[k] = int(vv) if vv.isdigit() else vv
    return result


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
