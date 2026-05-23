"""Tests for ProviderFactory Protocol."""


class _SimpleFactory:
    async def create_provider(self, config):
        return None  # type: ignore[return-value]


def test_factory_protocol_satisfied() -> None:
    factory = _SimpleFactory()
    assert hasattr(factory, "create_provider")
