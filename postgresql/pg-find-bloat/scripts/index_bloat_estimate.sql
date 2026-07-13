-- 降级估算模式：不依赖 pgstattuple 扩展
-- 原理：假设 btree 索引理想填充密度约 90%，用 reltuples * 单条目估算宽度(此处保守取 40 字节，
-- 含 6 字节 item pointer + 索引键平均宽度的粗略近似) / 0.9 作为理论大小，
-- 与实际大小比较得到粗略膨胀估算
-- 注意：这是非常粗略的估算，仅用于无法安装 pgstattuple 时的初筛；
-- 精确判断请优先使用 index_bloat_pgstattuple.sql

with index_info as (
    select
        n.nspname as schema_name,
        ic.relname as object_name,
        t.relname as table_name,
        ic.reltuples,
        pg_relation_size(ic.oid) as real_size
    from pg_class ic
    join pg_index idx on idx.indexrelid = ic.oid
    join pg_class t on t.oid = idx.indrelid
    join pg_namespace n on n.oid = ic.relnamespace
    join pg_am am on am.oid = ic.relam and am.amname = 'btree'
    where ic.relkind = 'i'
      and n.nspname not in ('pg_catalog', 'information_schema')
      and pg_relation_size(ic.oid) >= 8 * 1024 * 1024
)
select
    current_database() as database,
    schema_name,
    object_name,
    'index'::text as object_type,
    table_name,
    reltuples::bigint as row_estimate,
    real_size,
    greatest(
        round(real_size - (reltuples * 40 / 0.9)),
        0
    )::bigint as bloat_size,
    round(
        greatest(real_size - (reltuples * 40 / 0.9), 0)
        / nullif(real_size, 0) * 100,
        1
    ) as bloat_ratio
from index_info
order by bloat_size desc;
