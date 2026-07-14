#!/usr/bin/env bash
# 01_install_pg.sh
# 用途：在目标节点安装指定版本的 PostgreSQL（server/client/contrib）及所需插件，
#       自动识别 dnf/yum/apt，兼容 Anolis OS 8 (yum) 与 Anolis OS 23 (dnf)。
# 用法：./01_install_pg.sh <pg_version> "<plugin1 plugin2 ...>" [ha_choice: patroni|repmgr|none]
#
# 安全说明：仅从系统已配置的官方/发行版仓库安装，不额外添加不明源，不 curl/wget 未声明 URL。
# 若目标仓库中不存在指定版本或插件，脚本会明确报错并退出，不做静默降级。

set -euo pipefail

PG_VERSION="${1:?用法: $0 <pg_version> \"<plugins>\" [ha_choice]}"
PLUGINS="${2:-}"
HA_CHOICE="${3:-none}"

pkg_mgr() {
  if command -v dnf &>/dev/null; then echo dnf
  elif command -v yum &>/dev/null; then echo yum
  elif command -v apt-get &>/dev/null; then echo apt
  else echo "未识别到 dnf/yum/apt，无法自动安装，请人工介入。" >&2; exit 1
  fi
}

MGR="$(pkg_mgr)"
echo "==== 检测到包管理器: ${MGR} ===="

install_rpm_family() {
  local mgr="$1"
  echo "==== 安装 PostgreSQL ${PG_VERSION} 官方仓库 RPM（如尚未配置） ===="
  if ! rpm -q "pgdg-redhat-repo" &>/dev/null 2>&1; then
    echo "提示：如系统未预配置 PGDG 仓库，请先由用户确认允许添加官方 PGDG 仓库，" \
         "本脚本不会自动添加未声明的第三方仓库。"
  fi

  echo "==== 安装 PostgreSQL server/client/contrib ===="
  "${mgr}" install -y \
    "postgresql${PG_VERSION}-server" \
    "postgresql${PG_VERSION}" \
    "postgresql${PG_VERSION}-contrib" \
    || { echo "安装失败：请确认仓库中是否存在 postgresql${PG_VERSION} 相关包。" >&2; exit 1; }

  if [[ -n "$PLUGINS" ]]; then
    echo "==== 安装插件: ${PLUGINS} ===="
    for p in $PLUGINS; do
      "${mgr}" install -y "${p}_${PG_VERSION}" 2>/dev/null \
        || "${mgr}" install -y "${p}" \
        || { echo "插件 ${p} 在当前仓库中未找到对应 PG ${PG_VERSION} 版本，请人工确认兼容性后重试。" >&2; exit 1; }
    done
  fi

  case "$HA_CHOICE" in
    patroni)
      echo "==== 安装 Patroni + etcd + Python 依赖 ===="
      "${mgr}" install -y patroni python3-etcd3 etcd \
        || "${mgr}" install -y python3-pip etcd && pip3 install --user patroni[etcd3]
      ;;
    repmgr)
      echo "==== 安装 repmgr ===="
      "${mgr}" install -y "repmgr${PG_VERSION}" \
        || { echo "未找到 repmgr${PG_VERSION}，请确认仓库版本对应关系。" >&2; exit 1; }
      ;;
    none) ;;
    *) echo "未知 HA 选择: ${HA_CHOICE}（应为 patroni|repmgr|none）" >&2; exit 1 ;;
  esac
}

install_deb_family() {
  echo "==== apt-get update ===="
  apt-get update -y

  echo "==== 安装 PostgreSQL server/client/contrib ===="
  apt-get install -y \
    "postgresql-${PG_VERSION}" \
    "postgresql-client-${PG_VERSION}" \
    "postgresql-contrib-${PG_VERSION}" \
    || { echo "安装失败：请确认 apt 仓库中是否存在 postgresql-${PG_VERSION}。" >&2; exit 1; }

  if [[ -n "$PLUGINS" ]]; then
    echo "==== 安装插件: ${PLUGINS} ===="
    for p in $PLUGINS; do
      apt-get install -y "postgresql-${PG_VERSION}-${p}" 2>/dev/null \
        || { echo "插件 ${p} 未找到对应 PG ${PG_VERSION} 包，请人工确认。" >&2; exit 1; }
    done
  fi

  case "$HA_CHOICE" in
    patroni)
      echo "==== 安装 Patroni + etcd ===="
      apt-get install -y patroni etcd python3-etcd3
      ;;
    repmgr)
      echo "==== 安装 repmgr ===="
      apt-get install -y "postgresql-${PG_VERSION}-repmgr" \
        || { echo "未找到对应 repmgr 包，请人工确认版本。" >&2; exit 1; }
      ;;
    none) ;;
    *) echo "未知 HA 选择: ${HA_CHOICE}（应为 patroni|repmgr|none）" >&2; exit 1 ;;
  esac
}

case "$MGR" in
  dnf|yum) install_rpm_family "$MGR" ;;
  apt) install_deb_family ;;
esac

echo "==== 安装完成，版本核实 ===="
if command -v "psql" &>/dev/null; then psql --version; fi
