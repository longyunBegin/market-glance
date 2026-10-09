#!/bin/bash
# market-glance 健康检查（由 market-glance-healthcheck.timer 每 10 分钟跑一次）：
#  - 页面服务 :8090 无响应（进程假死）→ 重启 www 服务
#  - 隧道服务不在运行 → 拉起
# 进程崩溃由 systemd Restart=always 兜底；本脚本只处理"活着但没响应"的情况。
set -u
if ! curl -fsS -m 10 -o /dev/null http://127.0.0.1:8090/; then
  echo "$(date '+%F %T') 页面 :8090 无响应，重启 market-glance-www.service"
  systemctl restart market-glance-www.service || true
fi
if ! systemctl is-active -q market-glance-tunnel.service; then
  echo "$(date '+%F %T') 隧道服务未运行，尝试启动 market-glance-tunnel.service"
  systemctl start market-glance-tunnel.service || true
fi
exit 0
