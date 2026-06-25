"""Single source of truth for the package version string.

Lives in its own leaf module so submodules (window, preferences,
updates, snippets_dialog) can import ``__version__`` without dragging
``clipman/__init__.py`` into their import graph and creating a
cyclic dependency that CodeQL flags as ``py/cyclic-import``.

``clipman/__init__.py`` re-exports ``__version__`` from here so the
public attribute ``clipman.__version__`` still works for callers that
expect it (tests, CLI ``--version``, pyproject metadata).

``scripts/bump-version.sh`` patches the literal in this file.
"""

__version__ = "1.0.6"
