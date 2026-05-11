"""
wcwidth - Determine printable width of a Unicode character on a terminal.
"""

from .wcwidth import (
    wcwidth,
    wcswidth,
    list_versions,
    _bisearch,
    _wcmatch_version,
    _wcversion_value,
    WIDE_EASTASIAN,
    ZERO_WIDTH,
    VS16_NARROW_TO_WIDE,
)

__version__ = '0.6.0'

__all__ = ('wcwidth', 'wcswidth', 'list_versions')
