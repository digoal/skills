-- 需要已安装 pgstattuple 扩展（提供 pgstatindex 函数）
-- avg_leaf_density 是叶子页的平均填充密度，100 - avg_leaf_density 近似为可回收空闲比例
-- 仅适用于 btree 索引；GIN/GiST/BRIN 等其他索引类型请改用估算模式或专用工具
-- 已过滤实际大小 < 8MB 的索引，避免小索引噪音

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
        * (100 - psi.avg_leaf_density) / 100
    )::bigint                                                        as bloat_size,
    round((100 - psi.avg_leaf_density)::numeric, 1)                  as bloat_ratio
from pg_class ic
join pg_index idx on idx.indexrelid = ic.oid
join pg_class t on t.oid = idx.indrelid
join pg_namespace n on n.oid = ic.relnamespace
join pg_am am on am.oid = ic.relam and am.amname = 'btree'
cross join lateral pgstatindex(ic.oid) as psi
where ic.relkind = 'i'
  and n.nspname not in ('pg_catalog', 'information_schema')
  and pg_relation_size(ic.oid) >= 8 * 1024 * 1024
order by bloat_size desc;
