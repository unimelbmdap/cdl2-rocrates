"""Check for the optional dependencies behind the ``validate`` extra."""

from __future__ import annotations


def require_validate_extra() -> None:
    """Raise ``ImportError`` if the ``validate`` extra is not installed."""
    try:
        import rdflib  # noqa: F401
        import validators  # noqa: F401
    except ImportError as exc:
        msg = (
            "MASP validation needs optional dependencies. "
            'Install them with: pip install "crategraph[validate]"'
        )
        raise ImportError(msg) from exc
