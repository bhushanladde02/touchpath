"""Sphinx configuration for the touchpath documentation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

project = "touchpath"
author = "Bhushan Ladde"
copyright = "2026, Bhushan Ladde"
release = "0.1.0"
version = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

source_suffix = {".rst": "restructuredtext"}
master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "_convert.py"]

# ----------------------------------------------------------------- autodoc
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autodoc_preserve_defaults = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# ------------------------------------------------------------------- theme
# Sphinx emits the "failed to reach any of the inventories" warning untyped,
# so suppress_warnings cannot target it and -W would fail the docs deploy over
# an unreachable docs.python.org. The CI workflow filters that one line out
# instead and fails on everything else. Keep the timeout short so a dead
# inventory host costs seconds, not minutes.
intersphinx_timeout = 10

html_baseurl = "https://bhushanladde02.github.io/touchpath/"
html_theme = "furo"
html_title = "touchpath"
html_static_path = ["_static"]
html_theme_options = {
    "source_repository": "https://github.com/bhushanladde02/touchpath/",
    "source_branch": "main",
    "source_directory": "docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/bhushanladde02/touchpath",
            "class": "",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" viewBox="0 0 16 16">'
                '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38'
                "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13"
                "-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66"
                ".07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15"
                "-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 "
                "1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 "
                "1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 "
                '1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>'
                "</svg>"
            ),
        },
    ],
}

html_css_files = ["custom.css"]
