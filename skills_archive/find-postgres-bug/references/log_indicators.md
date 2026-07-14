# PG Log Indicators

`build_and_start_pg.sh` configures the server with verbose logging
(`log_min_messages = debug1`, `log_statement = 'all'`,
`log_line_prefix = '%m [%p] %q%u@%d from %h '`).

This reference explains what to grep for.

## Severity levels (ascending)

`DEBUG1..DEBUG5` < `INFO` < `NOTICE` < `LOG` < `WARNING` < `ERROR`
< `FATAL` < `PANIC`

For bug hunting, treat anything `WARNING` or above as a candidate.

## Useful single-line greps

```bash
# Anything bad
grep -E '^(ERROR|FATAL|PANIC|WARNING):' "$PG_LOG"

# Server-side crashes
grep -E '^(FATAL|PANIC):' "$PG_LOG"
grep -E 'server closed the connection unexpectedly' "$PG_LOG"
grep -E 'Could not open relation mapping file' "$PG_LOG"

# Assertions (only fires with --enable-cassert)
grep -E 'TRAP:|Assert|FailedAssertion' "$PG_LOG"

# Buffer / page corruption
grep -E 'invalid page header|invalid tuple|read leftover|xid wrap' "$PG_LOG"

# Lock waits / deadlocks
grep -E 'deadlock detected|still waiting for' "$PG_LOG"

# OOM / disk
grep -E 'out of memory|No space left on device|ENOSPC' "$PG_LOG"

# Replication / WAL
grep -E 'WAL was generated|invalid magic number|could not read' "$PG_LOG"
grep -E 'replication slot|walreceiver|walsender' "$PG_LOG"
```

## Multi-line pattern — error context

`ERROR:` lines are followed by a `CONTEXT:` block, then a
`STATEMENT:` line. Capture all three together:

```bash
awk '/^(ERROR|FATAL|PANIC):/{flag=1; out=""} flag{out=out $0 ORS}
     /^STATEMENT:/{print out; flag=0; out=""}' "$PG_LOG"
```

The `STATEMENT:` line is the exact SQL that triggered the error —
**always include it in the bug report**.

## Multi-line pattern — backtrace

`FATAL` from a server crash is followed by a backtrace:

```
LOG:  server process (PID 12345) was terminated by signal 11: Segmentation fault
LOG:  terminating any other active server processes
```

And in `log_line_prefix = '%m [%p]'` the `[12345]` is the PID you
attach `gdb` to. On Linux, `gcore <pid>` while the backend is still
running, or wait for a core file in `$PGDATA`.

## Multi-line pattern — assertion

```
TRAP: FailedAssertion("!((*tuple)->t_data->t_infomask & HEAP_XMAX_INVALID)", File: "heapam.c", Line: 6782)
```

The file:line is the exact assertion site. This is a near-perfect
bug report even before you write a `.sql` repro.

## Reading the log_line_prefix

With `log_line_prefix = '%m [%p] %q%u@%d from %h '`:

- `%m` — timestamp with milliseconds
- `[12345]` — backend PID
- `%q` — quiet (nothing in normal sessions)
- `alice@orders` — user@database
- `from 192.0.2.10` — client IP / socket

When the user/database/IP is empty (`@` or `from` followed by space),
the connection came from a maintenance process (autovacuum,
walsender, etc.).

## Capture script

`capture_log.sh` implements the most common greps. Use it directly:

```bash
./capture_log.sh errors     # only ERROR/FATAL/PANIC/WARNING lines
./capture_log.sh tail 500   # last 500 raw lines
```
