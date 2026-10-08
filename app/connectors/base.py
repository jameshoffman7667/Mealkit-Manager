from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


class ConnectorError(Exception):
    """The service site did not behave as expected. Nothing is assumed to have changed."""


class NeedsVerification(ConnectorError):
    """The site asked for a one-time code, CAPTCHA or similar. It is never bypassed."""


@dataclass
class RemoteState:
    status: str                                   # active | paused | cancelled
    weeks: dict = field(default_factory=dict)     # Monday date -> delivering | skipped | paused
    pending_issue: str = ""                       # set when a payment problem or pending order is visible
    evidence: str = ""                            # short, non-personal summary for the activity log


class Connector(ABC):
    """One signed-in session on a service's website. Use as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        pass

    @abstractmethod
    def read_state(self, today: date) -> RemoteState: ...

    @abstractmethod
    def skip(self, week: date) -> None: ...

    @abstractmethod
    def unskip(self, week: date) -> None: ...

    @abstractmethod
    def reactivate(self) -> None: ...

    @abstractmethod
    def cancel(self) -> None: ...
