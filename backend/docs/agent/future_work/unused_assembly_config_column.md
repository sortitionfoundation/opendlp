# The unused `assemblies.config` column

Turned up while planning `1282-clone-cli`. Written to be pasted into an issue.

## Problem

`assemblies` has a `config` JSON column (`adapters/orm.py`), created by the
initial migration with the comment "JSON column for flexible assembly
configuration". Nothing reads or writes it:

- the `Assembly` domain model has no `config` attribute, and its constructor
  and `create_detached_copy` never mention one;
- no service, blueprint or test refers to `assembly.config` or
  `assemblies.c.config`.

`map_imperatively` maps every column of the table, so SQLAlchemy does add a
`config` attribute to loaded `Assembly` instances - which is how it could come
back into use by accident, as an untyped grab-bag that skips the domain model.

Every column we keep is one more thing to think about when cloning, exporting
or erasing a project: the clone plan had to stop and check whether it carried
anything.

## Proposal

Drop it. Check production first that every row is NULL
(`SELECT count(*) FROM assemblies WHERE config IS NOT NULL`).

Dropping a column has to be split across two releases, per
[Writing Migrations for Zero Downtime Deploys](../../deploy.md#writing-migrations-for-zero-downtime-deploys):

1. Remove the `Column("config", ...)` from `orm.assemblies`, so the running
   code no longer selects it. No migration in this release.
2. In the next release, an Alembic migration that drops the column.
