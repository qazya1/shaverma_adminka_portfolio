"""Minimal mappings onto tables owned by the shaverma project itself.

Nothing under this package is part of adminka's own schema: there is no
Alembic migration here, and `ExternalBase.metadata` is never passed to
Alembic as `target_metadata` (see app/models/base.py and
backend/migrations/env.py for the tables adminka actually owns).
"""
