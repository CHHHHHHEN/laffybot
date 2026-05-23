"""Tests for ProviderFactory Protocol."""


class _SimpleFactory:
    async def create_provider(self, config: object) -> None:
        return None


def test_factory_protocol_satisfied() -> None:
    factory = _SimpleFactory()
    assert hasattr(factory, "create_provider")
