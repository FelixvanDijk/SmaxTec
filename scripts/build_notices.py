"""Build a versioned runtime inventory and collect vendor notices for distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def runtime_packages(requirements: list[str]) -> list[str]:
    """Resolve installed runtime dependencies, excluding optional developer extras."""
    pending = list(requirements)
    visited: set[str] = set()
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(requirement.name)
        if name in visited:
            continue
        visited.add(name)
        pending.extend(distribution(name).requires or [])
    return sorted(visited)


def build_notices(destination: Path) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    # Setuptools can be collected by PyInstaller runtime hooks; include its notices too.
    names = runtime_packages([*project["dependencies"], "setuptools"])
    destination.mkdir(parents=True, exist_ok=True)
    license_root = destination / "licenses"
    license_root.mkdir(exist_ok=True)
    components = []
    for name in names:
        package = distribution(name)
        package_root = license_root / name
        notices = []
        for source_name in sorted(package.files or [], key=str):
            normalized = str(source_name).replace("\\", "/")
            # Wheel metadata contains the vendor-supplied license/notice files.
            if ".dist-info/" not in normalized or not re.search(
                r"(?:license|licence|copying|notice|authors)", normalized, re.IGNORECASE
            ):
                continue
            relative = normalized.split(".dist-info/", 1)[1]
            if ".." in Path(relative).parts:
                raise ValueError(f"Unsafe notice path for {name}")
            source = Path(package.locate_file(source_name))
            if not source.is_file():
                continue
            target = package_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            notices.append(target.relative_to(destination).as_posix())
        components.append(
            {
                "name": package.metadata["Name"],
                "version": package.version,
                "license": package.metadata.get("License-Expression")
                or package.metadata.get("License")
                or "See vendor notices",
                "project_urls": package.metadata.get_all("Project-URL") or [],
                "notice_files": notices,
            }
        )

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python's runtime LICENSE.txt was not found.")
    shutil.copyfile(python_license, license_root / "Python-LICENSE.txt")
    for source in sorted((ROOT / "packaging" / "licenses").glob("*.txt")):
        shutil.copyfile(source, license_root / source.name)

    # These notices cover the embedded Node driver and Playwright's bundled dependencies.
    driver = Path(distribution("playwright").locate_file("playwright/driver"))
    for relative in (
        "LICENSE",
        "package/LICENSE",
        "package/NOTICE",
        "package/ThirdPartyNotices.txt",
    ):
        source = driver / relative
        if not source.is_file():
            raise RuntimeError(f"Playwright's required vendor notice is missing: {relative}")
        target = license_root / "playwright-driver" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    inventory = {
        "application": project["name"],
        "version": project["version"],
        "python": platform.python_version(),
        "components": components,
        "notice_sha256": {
            path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(license_root.rglob("*"))
            if path.is_file()
        },
    }
    (destination / "dependency-inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    intro = (ROOT / "packaging" / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    rows = [f"{item['name']} {item['version']} — {item['license']}" for item in components]
    (destination / "THIRD_PARTY_NOTICES.txt").write_text(
        f"{intro}\n\nBUILD INVENTORY\nPython {platform.python_version()}\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    print(f"Collected runtime notices for {len(components)} Python distributions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build_notices(parser.parse_args().output)
