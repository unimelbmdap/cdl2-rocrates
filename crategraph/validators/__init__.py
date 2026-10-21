"""Validator plugins for checking data quality and compliance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crategraph.validators.errors import UnknownValidatorError

if TYPE_CHECKING:
    from collections.abc import Callable

    from crategraph.core.interfaces import Validator

_REGISTRY: dict[str, Callable[..., Validator]] = {}


def register_validator(kind: str, factory: Callable[..., Validator]) -> None:
    """Register *factory* under *kind* for lookup via get_validator."""
    _REGISTRY[kind] = factory


def get_validator(kind: str) -> Callable[..., Validator]:
    """Return the validator factory registered under *kind*.

    Raises:
        UnknownValidatorError: if no validator is registered for *kind*.
    """
    try:
        return _REGISTRY[kind]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        msg = f"Unknown validator kind {kind!r}. Known kinds: {known}."
        raise UnknownValidatorError(msg) from exc


def list_kinds() -> list[str]:
    """Return the names of all registered validator kinds, sorted."""
    return sorted(_REGISTRY)


def _masp_factory(profile: Any = None, **kwargs: Any) -> Validator:
    """Build a MaspValidator, importing it lazily (it needs the extra)."""
    from crategraph.validators.masp import MaspValidator

    return MaspValidator(profile, **kwargs)


register_validator("masp", _masp_factory)

__all__ = ["UnknownValidatorError", "get_validator", "list_kinds", "register_validator"]
