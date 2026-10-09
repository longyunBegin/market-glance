#!/bin/bash
# 安装 market-glance 的 systemd 服务：
#  - market-glance-fetch.timer     每 5 分钟拉一次 Yahoo 行情写 JSON
#  - market-glance-www.service     页面服务（:8090，静态 + /api/config + /api/klines）
#  - market-glance-tunnel.service  SSH 反向隧道（Mac localhost:8090）
#  - market-glance-healthcheck.*   每 10 分钟自检：:8090 无响应则重启 www
# 源文件在 ~/workspace/market-glance/systemd/（~ 持久保存）；
# 本脚本把它们装到 /etc/systemd/system/（VM 整体重建后需重跑一次本脚本）。
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
for u in market-glance-fetch.service market-glance-fetch.timer market-glance-www.service market-glance-tunnel.service market-glance-healthcheck.service market-glance-healthcheck.timer; do
  install -m 0644 "$SRC/$u" "/etc/systemd/system/$u"
done
chmod +x /home/hatch/workspace/market-glance/healthcheck.sh /home/hatch/workspace/market-glance/tunnel.sh
systemctl daemon-reload
# 出口代理（含凭证）只注入 systemd manager 内存，不写进任何文件（凭证不落盘）。
# 两个服务的 unit 文件里不再写代理，由这里统一注入；VM 重建后重跑本脚本即可恢复。
if [ -n "${HTTPS_PROXY:-}" ]; then
  systemctl set-environment \
    "https_proxy=${https_proxy:-}" "HTTPS_PROXY=${HTTPS_PROXY:-}" \
    "http_proxy=${http_proxy:-}" "HTTP_PROXY=${HTTP_PROXY:-}" \
    "all_proxy=${all_proxy:-}" "ALL_PROXY=${ALL_PROXY:-}"
  echo "proxy injected into systemd manager environment (memory only)"
else
  echo "WARN: 当前 shell 没有 HTTPS_PROXY，服务将无代理直连（Yahoo 会 SSL 报错）"
fi
systemctl enable --now market-glance-fetch.timer market-glance-www.service market-glance-tunnel.service market-glance-healthcheck.timer
# 配置变更后重启 www 服务，确保新环境变量生效
systemctl restart market-glance-www.service
# 立刻跑一次抓取，免得等 5 分钟才有数据
systemctl start market-glance-fetch.service || true
echo "installed + enabled + started"
systemctl is-enabled market-glance-fetch.timer market-glance-www.service market-glance-tunnel.service market-glance-healthcheck.timer
