-- 列出实例下所有可连接的非模板数据库
select datname
from pg_database
where datistemplate = false
  and datallowconn = true
order by datname;
