from pathlib import Path

from tools.platform_compat import get_host_temp_path


def test_get_host_temp_path_uses_named_temp_dir():
    path = get_host_temp_path("sample.txt")
    assert path.name == "sample.txt"
    assert path.parent.exists()
    assert path.parent.name == "hermes"


def test_get_host_temp_path_is_stable_for_same_name():
    first = get_host_temp_path("same.txt")
    second = get_host_temp_path("same.txt")
    assert isinstance(first, Path)
    assert first == second
