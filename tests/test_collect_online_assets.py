import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "collect_online_assets.py"
SPEC = spec_from_file_location("collect_online_assets", MODULE_PATH)
collector = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


def test_is_official_asset_url_allows_only_https_same_base():
    assert collector._is_official_asset_url(
        "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API",
        "https://developer.mozilla.org/en-US/docs/Web/",
    )
    assert not collector._is_official_asset_url(
        "http://developer.mozilla.org/en-US/docs/Web/API/Fetch_API",
        "https://developer.mozilla.org/en-US/docs/Web/",
    )
    assert not collector._is_official_asset_url(
        "https://example.com/en-US/docs/Web/API/Fetch_API",
        "https://developer.mozilla.org/en-US/docs/Web/",
    )


def test_extract_version_from_filename():
    assert collector._extract_version_from_filename("pandas-2.2.3-cp311-cp311-manylinux.whl") == "2.2.3"
    assert collector._extract_version_from_filename("pytest-8.3.3.tar.gz") == "8.3.3"
    assert collector._extract_version_from_filename("unknown.txt") is None
