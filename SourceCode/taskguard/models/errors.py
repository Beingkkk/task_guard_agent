"""TaskGuard exception hierarchy.

Relates-to: FR-1
"""


class TaskGuardError(Exception):
    """Base exception for all TaskGuard errors."""

    code: str = "taskguard_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class TaskRegistrationError(TaskGuardError):
    """Raised when a task cannot be registered."""

    code: str = "registration_error"


class TaskNotFoundError(TaskGuardError):
    """Raised when a referenced task does not exist."""

    code: str = "not_found"


class StorageError(TaskGuardError):
    """Raised when reading/writing persistent state fails."""

    code: str = "storage_error"


class CollectionError(TaskGuardError):
    """Raised when a collector fails to read log or process data."""

    code: str = "collection_error"
