"""Abstract base class every Extra Domain must implement."""
from abc import ABC, abstractmethod


class BaseDomain(ABC):

    @abstractmethod
    def get_id(self) -> str:
        """Unique domain identifier e.g. 'clipboard', 'mirror'."""
        ...

    @abstractmethod
    def get_actions(self) -> list[str]:
        """All action strings this domain handles e.g. ['copy', 'paste_add']."""
        ...

    @abstractmethod
    def execute(self, action: str, context, core_facade) -> dict:
        """Run *action* and return {'status': 'FINISHED'|'CANCELLED', 'message': str}."""
        ...
