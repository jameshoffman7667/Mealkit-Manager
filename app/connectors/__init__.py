"""Service connectors. FACTORY builds a connector for a service; tests replace it with a fake."""


def default_factory(service_id: str, email: str, password: str):
    from .profiles import get_profile
    from .web import WebConnector
    return WebConnector(get_profile(service_id), email, password)


FACTORY = default_factory
