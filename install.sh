#!/usr/bin/env bash
set -euo pipefail

FULL_INSTALL=false
if [[ ${1:-} == "--full" ]]; then
  FULL_INSTALL=true
elif [[ $# -gt 0 ]]; then
  echo "用法：sudo bash install.sh [--full]" >&2
  exit 1
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "请使用 sudo ./install.sh" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "当前安装器支持 Raspberry Pi OS、Ubuntu、Kali 等使用 apt 的树莓派系统。" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "未找到 systemd；无法安装开机服务。" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for file in pictl.py pictl-fan.service pictl-battery.service pictl-display.service pictl-time-sync.service pictl-time-sync.timer; do
  [[ -f "${SCRIPT_DIR}/${file}" ]] || { echo "缺少文件：${file}" >&2; exit 1; }
done

echo "[1/4] 安装系统依赖..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-gpiozero python3-smbus2 python3-pil i2c-tools

# Raspberry Pi OS/Ubuntu on newer boards prefer lgpio. Some Kali/Debian
# repositories do not provide this package, so install it only when available.
if apt-cache show python3-lgpio >/dev/null 2>&1; then
  apt-get install -y python3-lgpio
fi

echo "[2/4] 安装 PiCtl..."
install -d -m 0755 /usr/local/lib/pictl
install -m 0755 "${SCRIPT_DIR}/pictl.py" /usr/local/lib/pictl/pictl.py
ln -sfn /usr/local/lib/pictl/pictl.py /usr/local/bin/pictl
ln -sfn /usr/local/lib/pictl/pictl.py /usr/bin/pictl
install -m 0644 "${SCRIPT_DIR}/pictl-fan.service" /etc/systemd/system/pictl-fan.service
install -m 0644 "${SCRIPT_DIR}/pictl-battery.service" /etc/systemd/system/pictl-battery.service
install -m 0644 "${SCRIPT_DIR}/pictl-display.service" /etc/systemd/system/pictl-display.service
install -m 0644 "${SCRIPT_DIR}/pictl-time-sync.service" /etc/systemd/system/pictl-time-sync.service
install -m 0644 "${SCRIPT_DIR}/pictl-time-sync.timer" /etc/systemd/system/pictl-time-sync.timer

if [[ ! -f /etc/pictl.conf ]]; then
  cat >/etc/pictl.conf <<'EOF'
FAN_GPIO=13
FAN_ON_TEMP=60
FAN_OFF_TEMP=39
I2C_BUS=1
BATTERY_ADDRESS=0x66
BATTERY_REGISTER=0x01
BATTERY_CAPACITY_MAH=2600
BATTERY_CHARGE_MA=1000
BATTERY_DROP_PERCENT_PER_MIN=1
BATTERY_LOW=0
BATTERY_AUTO_SHUTDOWN=1
OLED_ADDRESS=0x3c
OLED_WIDTH=128
OLED_HEIGHT=32
OLED_ROTATE=0
OLED_PAGE_SECONDS=3
TIMEZONE=Asia/Shanghai
EOF
fi
[[ -f /etc/pictl-fan-mode ]] || printf 'auto\n' >/etc/pictl-fan-mode

echo "[3/4] 载入服务..."
systemctl daemon-reload

model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
if [[ "${model}" == *"Raspberry Pi"* ]]; then
  systemctl enable --now pictl-fan.service
  echo "检测到 ${model}，温控风扇服务已启动。"

  if [[ "${FULL_INSTALL}" == true ]]; then
    echo "正在配置完整硬件功能..."
    /usr/bin/pictl time setup
    systemctl enable pictl-display.service pictl-battery.service
    echo "OLED、逐次电量记录、0% 自动关机、RTC 和网络校时已设置为开机启动。"
  fi
else
  echo "未检测到 Raspberry Pi 硬件，程序已安装，但未启动 GPIO 风扇服务。"
fi

echo "[4/4] 完成。"
echo "运行 sudo pictl 打开中文菜单；运行 pictl status 查看状态。"
if [[ "${FULL_INSTALL}" == true ]]; then
  echo "请执行 sudo reboot，使 I²C、RTC、OLED 和全部服务生效。"
fi
