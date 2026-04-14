"""Errors raised by the writer subsystem."""

from __future__ import annotations


class UnknownFormatError(ValueError):
    """Raised when get_writer is called with an unregistered format name."""
