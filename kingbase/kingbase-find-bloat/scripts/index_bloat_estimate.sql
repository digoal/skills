-- 降级估算模式：不依赖 kbstattuple 扩展
-- 原理：假设 btree 索引理想填充密度约 90%，用 reltuples * 单条目估算宽度(此处保守取 40 字节，
-- 含 6 字节 item pointer + 索引键平均宽度的粗略近似) / 0.9 作为理论大小，
-- 与实际大小比较得到粗略膨胀估算
-- 注意：这是非常粗略的估算，仅用于无法安装 kbstattuple 时的初筛；
-- 精确判断请优先使用 index_bloat_kbstattuple.sql
-- KingbaseES 兼容：所有 round(x, 1) 均显式 cast 为 numeric（无 round(double, int) 重载）
-- 已排除 KingbaseES 系统 schema（sys_ 前缀）

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
      and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
      and n.nspname not like 'sys\_%'
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
        round(real_size::numeric - (reltuples::numeric * 40 / 0.9)),
        0
    )::bigint as bloat_size,
    round(
        greatest(real_size::numeric - (reltuples::numeric * 40 / 0.9), 0)
        / nullif(real_size, 0)::numeric * 100,
        1
    )::numeric as bloat_ratio
from index_info
order by bloat_size desc;
