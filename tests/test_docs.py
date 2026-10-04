"""Checks on the built documentation.

These exist because of a failure mode Sphinx does not report. reStructuredText
forbids nested inline markup, so ``**:doc:`overview`**`` is not a bold link —
docutils gives up and emits the inner markup as literal text. It does so
*silently*: no warning, exit code 0, and a ``-W`` build passes. The published
page then shows raw backticks and role names to every reader.

Eleven of these shipped to GitHub Pages before anyone looked at the rendered
page. Checking the source with a regex is unreliable (emphasis spanning two
separate spans looks identical to nesting), so these tests read the generated
HTML instead: if markup survived into the output, it was never processed.

Skipped when the docs have not been built. The CI workflow builds them first,
so there they always run.
"""

import re

import pytest

from pathlib import Path

BUILD = Path(__file__).resolve().parents[1] / "docs" / "_build" / "html"

# viewcode renders module source verbatim, so docstring markup appears there
# as a matter of course and is not a defect.
EXCLUDED = ("_modules",)

LITERAL = re.compile(r"``[^`<\n]+``")
ROLE = re.compile(r":(?:doc|func|mod|class|meth|attr|term|ref):`[^`<\n]+`")


def _pages():
    if not BUILD.is_dir():
        pytest.skip("docs not built; run: python -m sphinx -b html docs docs/_build/html")
    return [
        path
        for path in BUILD.rglob("*.html")
        if not any(part in EXCLUDED for part in path.parts)
    ]


def _offenders(pattern):
    found = []
    for page in _pages():
        for match in pattern.finditer(page.read_text(encoding="utf-8")):
            found.append(f"{page.relative_to(BUILD)}: {match.group(0)}")
    return found


def test_no_literal_markup_survives_into_the_html():
    """``code`` reaching the output means it was never converted."""
    offenders = _offenders(LITERAL)
    assert not offenders, (
        "raw inline-literal markup in the rendered docs — almost always a "
        "literal nested inside bold or italic, which rST does not allow:\n  "
        + "\n  ".join(offenders[:10])
    )


def test_no_role_markup_survives_into_the_html():
    """:doc:`page` reaching the output means the cross-reference is dead text."""
    offenders = _offenders(ROLE)
    assert not offenders, (
        "unprocessed roles in the rendered docs — these are not links, they "
        "are text that looks like markup to the reader:\n  "
        + "\n  ".join(offenders[:10])
    )


def test_the_guide_is_reachable_from_the_site():
    """The published docs are only useful if the portal points at them."""
    nav = (
        Path(__file__).resolve().parents[1]
        / "src" / "touchpath" / "web" / "templates" / "_nav.html"
    ).read_text()
    assert "bhushanladde02.github.io/touchpath" in nav


def test_every_page_links_to_the_documentation():
    """Not only the nav: a reader who scrolls should find it in the footer."""
    base = Path(__file__).resolve().parents[1] / "src" / "touchpath" / "web" / "templates"
    for name in ("about.html", "index.html", "datasets.html"):
        page = (base / name).read_text()
        assert "bhushanladde02.github.io/touchpath" in page, f"{name} has no docs link"
