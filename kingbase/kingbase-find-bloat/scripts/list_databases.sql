-- 列出 KingbaseES 实例下所有可连接的非模板数据库（PG 兼容模式，视图与 PG 一致）
select datname
from pg_database
where datistemplate = false
  and datallowconn = true
order by datname;
