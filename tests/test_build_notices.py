"""Distribution metadata must describe runtime packages without leaking local paths."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_notices", ROOT / "scripts/build_notices.py")
assert SPEC and SPEC.loader
NOTICES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NOTICES)


def test_runtime_inventory_excludes_inactive_markers_and_dev_extras():
    packages = NOTICES.runtime_packages(
        ["playwright", "pytest; extra == 'dev'", "not-installed; python_version < '2'"]
    )
    assert "playwright" in packages
    assert "pyee" in packages
    assert "greenlet" in packages
    assert "pytest" not in packages
    assert "not-installed" not in packages


def test_generated_notices_have_exact_versions_hashes_and_no_developer_paths(tmp_path):
    import hashlib

    NOTICES.build_notices(tmp_path)
    serialized = (tmp_path / "dependency-inventory.json").read_text(encoding="utf-8")
    inventory = json.loads(serialized)
    components = {item["name"].lower(): item for item in inventory["components"]}
    assert "xlsxwriter" in components
    assert "pytest" not in components
    assert "pyinstaller" not in components
    assert str(ROOT) not in serialized
    for name, expected in inventory["notice_sha256"].items():
        path = tmp_path / name
        assert path.is_relative_to(tmp_path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    assert (tmp_path / "licenses/Qt-LGPL-3.0.txt").is_file()
    assert (tmp_path / "licenses/Qt-GPL-3.0.txt").is_file()
    assert (tmp_path / "licenses/Python-LICENSE.txt").is_file()
    assert (tmp_path / "licenses/playwright-driver/package/ThirdPartyNotices.txt").is_file()
