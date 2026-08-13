"""Fallback pydensecrf shim for Trans.

The upstream package needs a C++ compiler on Windows. The manga translator only
needs these imports at startup; when CRF refinement is called, this shim returns
the input soft mask instead of failing.
"""
