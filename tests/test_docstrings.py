"""Checks the developer reference of the documentation (docs/pages/reference/).

Each public module has a page in docs/pages/reference/capiq/ holding one "::: capiq.<module>" line, which mkdocstrings renders from the
Google-style docstrings with griffe. Two things would go wrong without these tests:
- a new module without a page (or without a nav entry in docs/zensical.toml) is missing from the reference;
- griffe reports a malformed docstring, such as a parameter that is not in the signature or a parameter
  without a type, only as a log warning, and the documentation build passes anyway, even with --strict.

Run from the project root with: pytest tests
"""

import logging
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REFERENCE = ROOT / "docs" / "pages" / "reference" / "capiq"


def public_modules() -> list[str]:
    return sorted(path.stem for path in (SRC / "capiq").glob("*.py") if not path.stem.startswith("_"))


def nav_paths(entries) -> Iterator[str]:
    """Every page path in a nav list of docs/zensical.toml."""
    for entry in entries:
        for value in entry.values() if isinstance(entry, dict) else [entry]:
            if isinstance(value, list):
                yield from nav_paths(value)
            else:
                yield value


@pytest.mark.parametrize("module", public_modules())
def test_every_module_has_a_reference_page(module):
    page = REFERENCE / f"{module}.md"
    assert page.is_file(), f"Add {page.relative_to(ROOT)} with the line '::: capiq.{module}'"
    assert f"::: capiq.{module}\n" in page.read_text(encoding="utf-8"), f"{page.name} must render capiq.{module}"
    with open(ROOT / "docs" / "zensical.toml", "rb") as file:
        nav = tomllib.load(file)["project"]["nav"]
    assert f"reference/capiq/{module}.md" in nav_paths(nav), (
        f'Add {{ "{module}" = "reference/capiq/{module}.md" }} to "Developer reference" > "capiQ" '
        "in the nav of docs/zensical.toml"
    )


def public_objects(obj) -> Iterator:
    """The object and, recursively, its public members; imported names are documented where they are defined."""
    yield obj
    for name, member in obj.members.items():
        if name.startswith("_") or member.is_alias:
            continue
        yield from public_objects(member)


def test_docstrings_render_without_warnings(caplog):
    griffe = pytest.importorskip("griffe", reason="griffe comes with the documentation tools (uv sync)")
    package = griffe.load("capiq", search_paths=[SRC], docstring_parser="google")
    with caplog.at_level(logging.WARNING, logger="griffe"):
        for obj in public_objects(package):
            if obj.docstring is not None:
                obj.docstring.parse("google")
    warnings = [record.getMessage() for record in caplog.records if record.name.startswith("griffe")]
    assert not warnings, "Docstrings that would render wrongly in the developer reference:\n" + "\n".join(warnings)
