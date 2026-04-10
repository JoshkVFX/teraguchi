"""NvFBC capture subpackage — see nvfbc_backend.py for the public API."""

from .nvfbc_backend import NvFBCBackend, helper_available

__all__ = ["NvFBCBackend", "helper_available"]
