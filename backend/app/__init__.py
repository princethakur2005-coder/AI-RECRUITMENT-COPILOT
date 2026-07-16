"""Top-level `app` package initializer kept intentionally minimal.

Avoid importing `app.main` or heavy submodules here to allow importing
subpackages (e.g., `app.services.cache`) without triggering application
startup or circular import side-effects.
"""

__all__: list[str] = []
