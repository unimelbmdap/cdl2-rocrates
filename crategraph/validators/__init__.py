"""Validator plugins for checking data quality and compliance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crategraph.validators.errors import UnknownValidatorError
from crategraph.validators.masp import MaspValidator
from crategraph.validators.report import ValidationReport

if TYPE_CHECKING:
    from collections.abc import Callable

    from crategraph.core.interfaces import Validator

_REGISTRY: dict[str, Callable[..., Validator]] = {}


def register_validator(kind: str, factory: Callable[..., Validator]) -> None:
    """Register *factory* under *kind* for lookup via get_validator.

    The factory is called as ``factory(profile, **kwargs)`` and must return a
    :class:`~crategraph.core.interfaces.Validator`.
    """
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


register_validator("masp", MaspValidator)

__all__ = [
    "MaspValidator",
    "UnknownValidatorError",
    "ValidationReport",
    "get_validator",
    "list_kinds",
    "register_validator",
]
