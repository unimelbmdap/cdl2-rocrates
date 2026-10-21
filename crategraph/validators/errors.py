"""Errors raised by the validator subsystem."""

from __future__ import annotations


class UnknownValidatorError(ValueError):
    """Raised when get_validator is called with an unregistered kind."""
