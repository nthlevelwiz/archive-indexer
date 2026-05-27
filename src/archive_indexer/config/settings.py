# todo: load yaml should be in a util file

# from __future__ import annotations

# from pathlib import Path
# from typing import Any

# try:
#     import yaml  # type: ignore
# except Exception:  # pragma: no cover
#     yaml = None


# from ..core.yaml_parser import mini_yaml_parse


# def load_yaml(path: str | Path) -> dict[str, Any]:
#     p = Path(path)
#     text = p.read_text(encoding="utf-8")
#     if yaml is not None:
#         data = yaml.safe_load(text) or {}
#     else:
#         data = mini_yaml_parse(text)
#     if not isinstance(data, dict):
#         raise ValueError(f"Expected mapping in YAML: {p}")
#     return data
