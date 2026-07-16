"""Small explicit dependency-injection container."""

from collections.abc import Callable
from threading import RLock
from typing import Any, TypeVar, cast

T = TypeVar("T")
Provider = Callable[["Container"], Any]


class Container:
    """Registers lazy singleton providers by interface.

    This intentionally avoids a framework-specific DI library. Constructor
    injection remains the default inside modules; this container is used only
    at application boundaries.
    """

    def __init__(self) -> None:
        self._providers: dict[type[Any], Provider] = {}
        self._instances: dict[type[Any], Any] = {}
        self._lock = RLock()

    def register(self, interface: type[T], provider: Callable[["Container"], T]) -> None:
        with self._lock:
            self._providers[interface] = provider
            self._instances.pop(interface, None)

    def register_instance(self, interface: type[T], instance: T) -> None:
        with self._lock:
            self._instances[interface] = instance

    def resolve(self, interface: type[T]) -> T:
        with self._lock:
            if interface in self._instances:
                return cast(T, self._instances[interface])
            try:
                provider = self._providers[interface]
            except KeyError as exc:
                raise LookupError(f"No dependency registered for {interface.__name__}") from exc
            instance = provider(self)
            self._instances[interface] = instance
            return cast(T, instance)
