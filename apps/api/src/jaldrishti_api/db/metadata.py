"""Import all models and expose metadata for Alembic autogeneration."""

from jaldrishti.persistence import metadata

target_metadata = metadata

__all__ = ["target_metadata"]
