"""Turnkey SDK error classes."""

from enum import Enum
from typing import Optional, Any


class TurnkeyErrorCodes(str, Enum):
    """Error codes for Turnkey API errors."""

    NETWORK_ERROR = "NETWORK_ERROR"
    BAD_RESPONSE = "BAD_RESPONSE"
    ACTIVITY_FAILED = "ACTIVITY_FAILED"
    ACTIVITY_CONSENSUS_NEEDED = "ACTIVITY_CONSENSUS_NEEDED"
    ACTIVITY_RESULT_MISSING = "ACTIVITY_RESULT_MISSING"


class TurnkeyError(Exception):
    """Base exception for Turnkey SDK errors."""

    def __init__(
        self,
        message: str,
        code: Optional[TurnkeyErrorCodes] = None,
        cause: Optional[Any] = None,
    ):
        super().__init__(message)
        self.name = "TurnkeyError"
        self.code = code
        self.cause = cause


class TurnkeyNetworkError(TurnkeyError):
    """Exception raised for network-related errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[TurnkeyErrorCodes] = None,
        cause: Optional[Any] = None,
    ):
        super().__init__(message, code, cause)
        self.name = "TurnkeyNetworkError"
        self.status_code = status_code


class TurnkeyActivityError(TurnkeyError):
    """Exception raised when an activity does not complete.

    Raised when an activity ends as failed or rejected, when polling stops
    before the activity reaches a terminal status, or when a completed
    activity does not contain the expected result.

    Attributes:
        activity_id: ID of the activity. Use it to fetch the activity later
            with ``get_activity``.
        activity_status: Last status seen for the activity, for example
            ``ACTIVITY_STATUS_FAILED`` or ``ACTIVITY_STATUS_PENDING``.
        activity_type: Type of the activity, for example
            ``ACTIVITY_TYPE_CREATE_WALLET``.
        failure: Failure message that Turnkey returned, if any.
    """

    def __init__(
        self,
        message: str,
        activity_id: Optional[str] = None,
        activity_status: Optional[str] = None,
        activity_type: Optional[str] = None,
        failure: Optional[str] = None,
        code: Optional[TurnkeyErrorCodes] = TurnkeyErrorCodes.ACTIVITY_FAILED,
        cause: Optional[Any] = None,
    ):
        super().__init__(message, code, cause)
        self.name = "TurnkeyActivityError"
        self.message = message
        self.activity_id = activity_id
        self.activity_status = activity_status
        self.activity_type = activity_type
        self.failure = failure

    def __str__(self) -> str:
        text = self.message
        if self.failure:
            text += f": {self.failure}"
        details = [
            f"{label}={value}"
            for label, value in (
                ("activity_id", self.activity_id),
                ("status", self.activity_status),
                ("type", self.activity_type),
            )
            if value
        ]
        if details:
            text += f" ({', '.join(details)})"
        return text


class TurnkeyActivityConsensusNeededError(TurnkeyActivityError):
    """Exception raised when an activity needs more approvals.

    The activity is not failed. Store ``activity_id`` and fetch the activity
    again with ``get_activity`` after the required approvals are in place.
    """

    def __init__(
        self,
        message: str,
        activity_id: Optional[str] = None,
        activity_status: Optional[str] = None,
        activity_type: Optional[str] = None,
        failure: Optional[str] = None,
        code: Optional[TurnkeyErrorCodes] = TurnkeyErrorCodes.ACTIVITY_CONSENSUS_NEEDED,
        cause: Optional[Any] = None,
    ):
        super().__init__(
            message, activity_id, activity_status, activity_type, failure, code, cause
        )
        self.name = "TurnkeyActivityConsensusNeededError"
