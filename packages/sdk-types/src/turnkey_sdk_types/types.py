"""Non-generated Turnkey SDK types."""

from dataclasses import dataclass
from enum import Enum

from turnkey_api_key_stamper import TStamp


class RequestType(Enum):
    """The type of Turnkey API request."""

    QUERY = "query"
    ACTIVITY = "activity"
    ACTIVITY_DECISION = "activityDecision"


@dataclass
class SignedRequest:
    """A signed request ready to be sent to the Turnkey API."""

    url: str
    body: str
    stamp: TStamp
    type: RequestType = RequestType.QUERY
