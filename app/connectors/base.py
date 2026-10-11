"""Identity-source connector interface.

Manasetu never scrapes a government system and no live government API is used. The
backend depends only on this interface; the prototype ships `MockRegistryConnector`.
A production deployment would implement the same interface against an *approved*
interface (e-Prisons / NHAA-Integrated Portal) under a data-sharing agreement with
proper authentication and authorisation, and map only the minimum fields below.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class IdentityResult:
    status: str                    # found | not_found | unavailable
    record: Optional[Dict] = None  # populated only when status == "found"
    source_label: str = ""


class IdentityConnector(ABC):
    source_label: str = ""

    @abstractmethod
    def lookup(self, person_id: str) -> IdentityResult: ...

    @abstractmethod
    def events_for(self, person_id: str) -> List[Dict]: ...
