-- KingbaseES 精确模式：需要已安装 kbstattuple 扩展（提供 kbstatindex 函数）：
--   create extension if not exists kbstattuple;
-- avg_leaf_density 是叶子页的平均填充密度，100 - avg_leaf_density 近似为可回收空闲比例
-- 仅适用于 btree 索引；GIN/GiST/BRIN 等其他索引类型请改用估算模式或专用工具
-- 已过滤实际大小 < 8MB 的索引，避免小索引噪音；已排除 KingbaseES 系统 schema
-- 注意：KingbaseES 无 round(double precision, integer) 重载，所有 round(x, 1) 均显式 cast 为 numeric

select
    current_database()                                              as database,
    n.nspname                                                        as schema_name,
    ic.relname                                                       as object_name,
    'index'::text                                                    as object_type,
    t.relname                                                        as table_name,
    ic.reltuples::bigint                                             as row_estimate,
    pg_relation_size(ic.oid)                                         as real_size,
    round(
        pg_relation_size(ic.oid)::numeric
        * (100 - kbi.avg_leaf_density) / 100
    )::bigint                                                        as bloat_size,
    round((100 - kbi.avg_leaf_density)::numeric, 1)                  as bloat_ratio
from pg_class ic
join pg_index idx on idx.indexrelid = ic.oid
join pg_class t on t.oid = idx.indrelid
join pg_namespace n on n.oid = ic.relnamespace
join pg_am am on am.oid = ic.relam and am.amname = 'btree'
cross join lateral kbstatindex(ic.oid) as kbi
where ic.relkind = 'i'
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname not like 'sys\_%'
  and pg_relation_size(ic.oid) >= 8 * 1024 * 1024
order by bloat_size desc;
