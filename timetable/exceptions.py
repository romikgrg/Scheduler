"""Custom exceptions used across the timetable scheduler."""


class TimetableError(Exception):
    """Base class for every error raised by this package."""


class ValidationError(TimetableError, ValueError):
    """Raised when input data is malformed (bad hours, empty ids, etc.).

    Inherits from ValueError as well so that callers who only catch
    ValueError still behave sensibly.
    """


class UnknownReferenceError(TimetableError, KeyError):
    """Raised when a session points at a lecturer that does not exist."""


class NoFeasibleTimetableError(TimetableError):
    """Raised when no arrangement satisfies every hard constraint.

    Deliberately an error rather than a partial result: a caller must not
    be able to mistake an impossible problem for a solved one.
    """
