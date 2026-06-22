"""Exceptions for the featherweight_telemetry package."""


class FeatherweightError(Exception):
    """Base exception for all featherweight_telemetry errors."""


class SerialConnectionError(FeatherweightError):
    """Raised when a serial port cannot be opened or read."""


class ParseError(FeatherweightError):
    """Raised when a line cannot be parsed and strict mode is enabled."""


class ReplayError(FeatherweightError):
    """Raised when a log file cannot be opened or is invalid."""


class ExportError(FeatherweightError):
    """Raised when export of packets fails."""
