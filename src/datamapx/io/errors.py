"""I/O related exceptions."""


class CsvReadError(Exception):
    """Raised when CSV input or reference data cannot be read or normalized."""


class CsvWriteError(Exception):
    """Raised when output CSV data cannot be written safely."""
