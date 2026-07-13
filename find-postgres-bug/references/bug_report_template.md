# Bug Report Template

The on-disk template used by `gen_bug_report.sh` is
`assets/bug_report.md.template`. This file is the human-readable
spec: which fields exist, what each one means, and what to put in.

## Fields

| Field | Required | Source |
| --- | --- | --- |
| `title` | yes | your short, factual title — "Crash on VACUUM FULL of ...", not "PG is broken" |
| `commit` | yes | full `git rev-parse HEAD` hash from `$PG_SRC_DIR` |
| `branch` | yes | `git rev-parse --abbrev-ref HEAD`, e.g. `REL_16_STABLE` |
| `area` | yes | one of: parser / planner / executor / storage / replication / commands / catalog / utils / fdw / contrib / extension / guc / replication / index / partitioning / client / docs |
| `summary` | yes | 1-3 sentence factual description of the symptom |
| `why_bug` | yes | why this is a bug — point at the spec / docs / expected invariant it violates |
| `fix` | yes | your suggested patch direction, even if rough; this is optional in upstream reports but expected here |
| `severity` | yes | `low` / `medium` / `high` / `critical` (data loss / crash) |
| `repro_path` | yes | path to the `.sql` file you ran |
| `repro_sql` | yes | inline contents of the repro (`|` YAML block is fine) |
| `actual` | yes | what you actually saw — include the `ERROR:` / `FATAL:` text |
| `expected` | yes | what should have happened |
| `log_path` | yes | path to the captured server log (relative to `$PGDATA` or absolute) |
| `log_snippet_lines` | no (default 80) | how many trailing lines of the log to embed |

## YAML skeleton

```yaml
title: "Crash on VACUUM FULL of partitioned table with detached leaf"
commit: "abc1234"            # from `git -C $PG_SRC_DIR rev-parse HEAD`
branch: "REL_16_STABLE"
area: "executor / heap"
severity: "high"
summary: |
  VACUUM FULL of a partitioned table whose leaf partition was
  DETACHed CONCURRENTLY in a separate session causes the backend
  to segfault in heap_page_prune.
why_bug: |
  Per docs (command/vacuum.sgml), VACUUM FULL on a parent should
  skip detached leaves. The crash shows the parent still holds a
  reference to the detached relation's relfilenode.
fix: |
  In cluster_rel(), check the result of
  find_inheritance_children() against RelationGetRelid() before
  scheduling the rebuild. Alternative: gate the cluster on
  RELKIND_PARTITIONED_TABLE and refuse to recurse into leaves
  that have been detached since the lock was taken.
repro_path: "repro/vacuum_full_crash.sql"
repro_sql: |
  SET client_min_messages = debug1;
  CREATE TABLE p (id int) PARTITION BY RANGE (id);
  CREATE TABLE p1 PARTITION OF p FOR VALUES FROM (0) TO (1000);
  INSERT INTO p SELECT g FROM generate_series(1,999) g;
  -- in another session:
  --   ALTER TABLE p DETACH PARTITION p1 CONCURRENTLY;
  VACUUM FULL p;
actual: |
  ERROR:  server closed the connection unexpectedly
  ... FATAL:  terminating connection ...
expected: |
  VACUUM FULL completes; detached leaf is left untouched.
log_path: "log/server.log"
log_snippet_lines: 80
```

## Output file

`gen_bug_report.sh` writes to:

```
<cwd>/markdown/find_postgres_bug-<title-slug>-<YYYY-MM-DD>.md
```

The title slug is the title lowercased, spaces → `-`, non-alnum
stripped, truncated to 60 chars. Override with the second arg to
`gen_bug_report.sh`.

## Posting to the community

For a real post to pgsql-bugs@lists.postgresql.org the report should
also include:

- **Subject** — `[BUG] <one-line symptom>` (no emoji, no "please help").
- **Top-of-message** — environment table from the rendered report.
- **Repro** — the SQL, inline (do not attach .sql files; the list
  strips them).
- **Server log snippet** — exact `FATAL` / `ERROR` / backtrace lines
  (never the whole log file).
- **Patch (if any)** — attached as a `.txt` or inlined as a
  unified diff.

The skill's output is sufficient to drop straight into a pgsql-bugs
post with light editing.
