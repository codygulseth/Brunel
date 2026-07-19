from .interfaces import IntegrationAdapter


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, IntegrationAdapter] = {}

    def register(self, adapter: IntegrationAdapter) -> None:
        name = adapter.manifest.adapter_name
        if name in self._adapters:
            raise ValueError("Adapter already explicitly registered")
        self._adapters[name] = adapter

    def get(self, name: str) -> IntegrationAdapter:
        if name not in self._adapters:
            raise ValueError("Adapter implementation is not registered")
        return self._adapters[name]

    def manifests(self):
        return tuple(x.manifest for x in self._adapters.values())
