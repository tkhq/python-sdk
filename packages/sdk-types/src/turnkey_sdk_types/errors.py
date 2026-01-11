"""Turnkey SDK error classes."""

from enum import Enum
from typing import Optional, Any


class TurnkeyErrorCodes(str, Enum):
    """Error codes for Turnkey API errors."""

    NETWORK_ERROR = "NETWORK_ERROR"
    BAD_RESPONSE = "BAD_RESPONSE"


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
