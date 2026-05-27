from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    return urlparse(url).netloc


def _parse_scalar(value: str) -> Any:
    vv = value.strip()
    if vv.isdigit():
        return int(vv)
    try:
        return float(vv)
    except ValueError:
        return vv


def mini_yaml_parse(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = [ln.rstrip("\n") for ln in text.splitlines() if ln.strip()]

    current_top_list: list[dict[str, Any]] | None = None
    current_item: dict[str, Any] | None = None
    current_nested_list_key: str | None = None
    current_nested_item: dict[str, Any] | None = None

    for raw in lines:
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line.endswith(":"):
            key = line[:-1]
            result[key] = []
            current_top_list = result[key]
            current_item = None
            current_nested_list_key = None
            current_nested_item = None
            continue

        if line.startswith("- "):
            rest = line[2:]
            if indent <= 2:
                current_item = {}
                assert isinstance(current_top_list, list)
                current_top_list.append(current_item)
                current_nested_list_key = None
                current_nested_item = None
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    current_item[k.strip()] = _parse_scalar(v)
            else:
                assert current_item is not None and current_nested_list_key is not None
                nested_item: dict[str, Any] = {}
                current_item[current_nested_list_key].append(nested_item)
                current_nested_item = nested_item
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    nested_item[k.strip()] = _parse_scalar(v)
            continue

        if ":" in line and current_item is not None:
            k, v = line.split(":", 1)
            key = k.strip()
            if v.strip() == "":
                current_item[key] = []
                current_nested_list_key = key
                current_nested_item = None
            else:
                if indent > 2 and current_nested_item is not None:
                    current_nested_item[key] = _parse_scalar(v)
                else:
                    current_item[key] = _parse_scalar(v)

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
