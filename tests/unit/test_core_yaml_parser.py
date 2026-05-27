from archive_indexer.core.yaml_parser import mini_yaml_parse


def test_mini_yaml_parse_top_level_list_of_mappings():
    text = """
sources:
  - label: Local
    type: folder
    path: /tmp/archive
"""
    data = mini_yaml_parse(text)
    assert "sources" in data
    assert data["sources"][0]["label"] == "Local"
    assert data["sources"][0]["type"] == "folder"
