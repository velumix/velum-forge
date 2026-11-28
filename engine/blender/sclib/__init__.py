"""Backward-compatible `sclib` alias forwarding cleanly to `vflib`."""
import sys
import vflib

for _sub in vflib.__all__:
    sys.modules[f"sclib.{_sub}"] = getattr(vflib, _sub)

from vflib import *  # noqa: F401, F403
__version__ = vflib.__version__
__all__ = vflib.__all__
