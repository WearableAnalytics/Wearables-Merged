from typing import Any
from uuid import UUID


# TODO: standardize format and message /detail
class EntityNotFoundError(Exception):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity_type: str, entity_id: UUID | Any) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found")


class DuplicateEntityError(Exception):
    """Raised when attempting to create an entity that already exists or violates a unique constraint."""

    def __init__(self, entity_type: str, detail: str | None = None) -> None:
        self.entity_type = entity_type
        self.detail = detail
        message = f"{entity_type} already exists"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


class BadRequestError(Exception):
    """Raised when the request is invalid for the current db state."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ConflictError(Exception):
    """Raised when an operation cannot be completed due to a constraint violation or conflict."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
