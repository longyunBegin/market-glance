#!/bin/bash
# 反向隧道：把 VM 的 :8090 映射到用户 Mac 的 localhost:8090，
# 用户在 Mac 浏览器打开 http://localhost:8090 即可看 market-glance。
# 适用于 VM 与 Mac 之间经 Tailscale + 代理互通的场景；非此环境可用
# 任意能跑通的 ssh -R 命令替代（可设 TUNNEL_CMD 覆盖整条命令）。
# 断线 10 秒后自动重连。注意：VM 整体重建后需重跑本脚本。
set -u
while true; do
  echo "$(date '+%H:%M:%S') tunnel connecting..."
  if [ -n "${TUNNEL_CMD:-}" ]; then
    eval "$TUNNEL_CMD"
  else
    # 默认示例：把目标机器地址换成你自己的（可用 TUNNEL_CMD 覆盖整条命令）
    ssh -N -T \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
      -R 8090:localhost:8090 \
      user@your-mac-tailscale-ip
  fi
  echo "$(date '+%H:%M:%S') tunnel exited ($?), retry in 10s"
  sleep 10
done
