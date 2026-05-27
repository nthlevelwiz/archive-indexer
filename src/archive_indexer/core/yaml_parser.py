# todo: this should just be in parsers.py

# from __future__ import annotations

# from typing import Any
#

# def mini_yaml_parse(text: str) -> dict[str, Any]:
#     result: dict[str, Any] = {}
#     lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
#     current_list = None
#     current_item = None
#     for ln in lines:
#         if not ln.startswith(" ") and ln.endswith(":"):
#             key = ln[:-1]
#             result[key] = []
#             current_list = result[key]
#             current_item = None
#         elif ln.strip().startswith("- "):
#             current_item = {}
#             assert isinstance(current_list, list)
#             current_list.append(current_item)
#             rest = ln.strip()[2:]
#             if ":" in rest:
#                 k, v = rest.split(":", 1)
#                 current_item[k.strip()] = v.strip()
#         elif ":" in ln and current_item is not None:
#             k, v = ln.strip().split(":", 1)
#             vv = v.strip()
#             current_item[k] = int(vv) if vv.isdigit() else vv
#     return result
