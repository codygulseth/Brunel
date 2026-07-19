"""Oracle Primavera P6 adapter using Brunel's canonical integration and schedule services."""

from .adapter import PrimaveraP6Adapter

__all__ = ["PrimaveraP6Adapter", "PrimaveraP6Service"]


def __getattr__(name):
    if name == "PrimaveraP6Service":
        from .service import PrimaveraP6Service

        return PrimaveraP6Service
    raise AttributeError(name)
