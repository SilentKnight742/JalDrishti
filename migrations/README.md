# Database migrations

Migrations are the only supported way to change the canonical PostGIS schema.
The initial revision enables PostGIS and creates the Phase 1 geography tables,
provenance columns, uniqueness constraints, and GiST indexes.

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
```
