#!/usr/bin/env python3
"""Small Raspberry Pi fan, RTC and battery manager."""

import argparse
import datetime
import os
import socket
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFIG = Path("/etc/pictl.conf")
FAN_MODE = Path("/etc/pictl-fan-mode")
BATTERY_LOG = Path("/var/lib/pictl/battery.csv")
BATTERY_FULL_CONFIRM_SECONDS = 3
DEFAULTS = {
    "FAN_GPIO": "13",
    "FAN_ON_TEMP": "60",
    "FAN_OFF_TEMP": "39",
    "I2C_BUS": "1",
    "BATTERY_ADDRESS": "0x66",
    "BATTERY_REGISTER": "0x01",
    "BATTERY_LOW": "0",
    "BATTERY_AUTO_SHUTDOWN": "1",
    "OLED_ADDRESS": "0x3c",
    "OLED_WIDTH": "128",
    "OLED_HEIGHT": "32",
    "OLED_ROTATE": "0",
    "OLED_PAGE_SECONDS": "3",
    "TIMEZONE": "Asia/Shanghai",
}


def load_config():
    values = dict(DEFAULTS)
    if CONFIG.exists():
        for raw in CONFIG.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in values:
                values[key.strip()] = value.strip().strip('"\'')
    return values


def run(command, check=False):
    return subprocess.run(command, text=True, check=check)


def require_root():
    if os.geteuid() != 0:
        raise SystemExit("此操作需要管理员权限，请在命令前加 sudo。")


def temperature():
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if not path.exists():
        raise RuntimeError("未找到 CPU 温度接口；当前机器可能不是树莓派。")
    return int(path.read_text().strip()) / 1000.0


def service(name, action):
    require_root()
    run(["systemctl", action, name], check=True)


def service_active(name):
    result = subprocess.run(
        ["systemctl", "is-active", name], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout.strip() or "unknown"


def gpio_led(pin):
    try:
        from gpiozero import LED
        return LED(pin)
    except Exception as exc:
        raise RuntimeError(f"GPIO 初始化失败（BCM {pin}）：{exc}") from exc


def fan_daemon(args):
    cfg = load_config()
    pin = int(cfg["FAN_GPIO"], 0)
    on_temp = float(cfg["FAN_ON_TEMP"])
    off_temp = float(cfg["FAN_OFF_TEMP"])
    if off_temp >= on_temp:
        raise RuntimeError("FAN_OFF_TEMP 必须小于 FAN_ON_TEMP。")
    fan = gpio_led(pin)
    try:
        while True:
            mode = FAN_MODE.read_text().strip() if FAN_MODE.exists() else "auto"
            current = temperature()
            if mode == "on":
                fan.on()
            elif mode == "off":
                fan.off()
            elif current >= on_temp:
                fan.on()
            elif current <= off_temp:
                fan.off()
            time.sleep(3)
    finally:
        fan.off()
        fan.close()


def fan_command(mode):
    require_root()
    FAN_MODE.write_text(mode + "\n", encoding="ascii")
    run(["systemctl", "enable", "--now", "pictl-fan.service"], check=True)
    messages = {"auto": "温控风扇已启用。", "on": "风扇已强制开启。", "off": "风扇已强制关闭。"}
    print(messages[mode])


def battery_value():
    cfg = load_config()
    try:
        from smbus2 import SMBus
    except ImportError as exc:
        raise RuntimeError("缺少 python3-smbus2，请重新运行安装器。") from exc
    bus_no = int(cfg["I2C_BUS"], 0)
    address = int(cfg["BATTERY_ADDRESS"], 0)
    register = int(cfg["BATTERY_REGISTER"], 0)
    with SMBus(bus_no) as bus:
        value = bus.read_byte_data(address, register)
    if not 0 <= value <= 100:
        raise RuntimeError(f"读取到异常原始值 {value}，请检查 I²C 地址和寄存器配置。")
    return value


def battery_daemon(args):
    cfg = load_config()
    low = int(cfg["BATTERY_LOW"], 0)
    auto_shutdown = cfg["BATTERY_AUTO_SHUTDOWN"].lower() in ("1", "yes", "true", "on")
    low_count = 0
    BATTERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            value = battery_value()
            record_battery(value)
            print(f"电量：{value}%（本次循环已记录）", flush=True)
            if value <= low:
                print(f"警告：电量达到 {low}%", file=sys.stderr, flush=True)
                low_count += 1
                if auto_shutdown and low_count >= 3:
                    print(f"电量连续三次达到 {low}%，正在安全关机。", file=sys.stderr, flush=True)
                    run(["systemctl", "poweroff"], check=True)
                    return
            else:
                low_count = 0
        except Exception as exc:
            print(f"电量读取失败：{exc}", file=sys.stderr, flush=True)
        time.sleep(3)


def record_battery(value):
    now = int(time.time())
    if not BATTERY_LOG.exists():
        BATTERY_LOG.write_text("timestamp,percent\n", encoding="ascii")
    with BATTERY_LOG.open("a", encoding="ascii") as handle:
        handle.write(f"{now},{value:.2f}\n")


def battery_history():
    if not BATTERY_LOG.exists():
        return []
    points = []
    for line in BATTERY_LOG.read_text(encoding="ascii", errors="ignore").splitlines()[1:]:
        try:
            stamp, value = line.split(",", 1)
            points.append((int(stamp), float(value)))
        except (ValueError, TypeError):
            continue
    return points


def battery_is_charging(history):
    """Return true after a below-full reading rises to 100% for three seconds."""
    if not history or history[-1][1] != 100:
        return False
    run_start = len(history) - 1
    while run_start > 0 and history[run_start - 1][1] == 100:
        run_start -= 1
    rose_from_below_full = run_start > 0 and history[run_start - 1][1] < 100
    return (rose_from_below_full
            and history[-1][0] - history[run_start][0] >= BATTERY_FULL_CONFIRM_SECONDS)


def battery_session_history(history=None):
    """Return the active discharge cycle after a confirmed full charge.

    Charging is confirmed when a below-full reading rises to exactly 100%
    and remains there for at least three seconds. While it remains full,
    elapsed time stays at zero. Once it drops, timing starts from the final
    100% sample.
    """
    history = battery_history() if history is None else history
    if not history:
        return []
    confirmed_end = None
    full_run_start = None
    rose_from_below_full = False
    for index, (stamp, value) in enumerate(history):
        if value == 100:
            if full_run_start is None:
                full_run_start = index
                rose_from_below_full = index > 0 and history[index - 1][1] < 100
            if (rose_from_below_full
                    and stamp - history[full_run_start][0] >= BATTERY_FULL_CONFIRM_SECONDS):
                confirmed_end = index
        else:
            full_run_start = None
            rose_from_below_full = False

    if confirmed_end is None:
        return history

    # If the current confirmed 100% run is still active, do not count the
    # time spent connected to the charger as battery-use time.
    if (history[-1][1] == 100 and full_run_start is not None
            and confirmed_end >= full_run_start):
        return history[-1:]

    return history[confirmed_end:]


def battery_elapsed_text(history):
    if not history:
        return "USED 00:00"
    elapsed = max(0, history[-1][0] - history[0][0])
    hours, remainder = divmod(elapsed, 3600)
    return f"USED {hours:02d}:{remainder // 60:02d}"


class SSD1306:
    def __init__(self, bus_no, address, width, height):
        from smbus2 import SMBus
        self.bus = SMBus(bus_no)
        self.address, self.width, self.height = address, width, height
        multiplex = height - 1
        compins = 0x12 if height == 64 else 0x02
        self.command(0xAE, 0xD5, 0x80, 0xA8, multiplex, 0xD3, 0x00, 0x40,
                     0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, compins,
                     0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF)

    def command(self, *values):
        for value in values:
            self.bus.write_byte_data(self.address, 0x00, value)

    def show(self, image):
        self.command(0x21, 0, self.width - 1, 0x22, 0, self.height // 8 - 1)
        pixels = image.load()
        data = []
        for page in range(self.height // 8):
            for x in range(self.width):
                byte = 0
                for bit in range(8):
                    if pixels[x, page * 8 + bit]:
                        byte |= 1 << bit
                data.append(byte)
        for offset in range(0, len(data), 16):
            self.bus.write_i2c_block_data(self.address, 0x40, data[offset:offset + 16])

    def clear(self):
        from PIL import Image
        self.show(Image.new("1", (self.width, self.height)))

    def close(self):
        self.bus.close()


def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "no network"
    finally:
        sock.close()


def oled_frame(cfg, page=0):
    from PIL import Image, ImageDraw, ImageFont
    width, height = int(cfg["OLED_WIDTH"]), int(cfg["OLED_HEIGHT"])
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    def font(size):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            return ImageFont.load_default()
    try:
        battery = f"{battery_value()}%"
    except Exception:
        battery = "--"
    mode = FAN_MODE.read_text().strip() if FAN_MODE.exists() else "auto"
    full_history = battery_history()
    session_history = battery_session_history(full_history)
    charging = battery_is_charging(full_history)
    pages = [
        (datetime.datetime.now().strftime("TIME %H:%M:%S"),
         datetime.datetime.now().strftime("DATE %m-%d")),
        (f"CPU  {temperature():.1f} C", f"FAN  {mode.upper()}"),
        (f"BAT  {battery}", "CHARGING" if charging else battery_elapsed_text(session_history)),
        ("IP ADDRESS", local_ip()),
    ]
    lines = pages[page % len(pages)]
    size = 13 if height <= 32 else 24
    row_height = height // 2
    for index, line in enumerate(lines):
        current_font = font(size)
        box = draw.textbbox((0, 0), line, font=current_font)
        text_width, text_height = box[2] - box[0], box[3] - box[1]
        if text_width > width:
            small_size = max(8, int(size * width / text_width))
            current_font = font(small_size)
            box = draw.textbbox((0, 0), line, font=current_font)
            text_width, text_height = box[2] - box[0], box[3] - box[1]
        x = max(0, (width - text_width) // 2)
        y = index * row_height + max(0, (row_height - text_height) // 2 - box[1])
        draw.text((x, y), line, font=current_font, fill=255)
    if cfg["OLED_ROTATE"] == "180":
        image = image.rotate(180)
    return image


def display_daemon(args):
    cfg = load_config()
    display = SSD1306(int(cfg["I2C_BUS"], 0), int(cfg["OLED_ADDRESS"], 0),
                      int(cfg["OLED_WIDTH"]), int(cfg["OLED_HEIGHT"]))
    try:
        page = 0
        delay = max(1.0, float(cfg["OLED_PAGE_SECONDS"]))
        while True:
            display.show(oled_frame(cfg, page))
            page = (page + 1) % 4
            time.sleep(delay)
    finally:
        display.clear()
        display.close()


def display_command(action):
    if action in ("on", "off"):
        service("pictl-display.service", "enable" if action == "on" else "disable")
        service("pictl-display.service", "start" if action == "on" else "stop")
        print("OLED 显示已启用。" if action == "on" else "OLED 显示已关闭。")
    elif action == "test":
        require_root()
        cfg = load_config()
        display = SSD1306(int(cfg["I2C_BUS"], 0), int(cfg["OLED_ADDRESS"], 0),
                          int(cfg["OLED_WIDTH"]), int(cfg["OLED_HEIGHT"]))
        try:
            display.show(oled_frame(cfg, 0))
        finally:
            display.close()
        print("测试画面已发送到 OLED。")
    else:
        print(service_active("pictl-display.service"))


def rtc_setup():
    require_root()
    config_candidates = [Path("/boot/firmware/config.txt"), Path("/boot/config.txt")]
    boot_config = next((p for p in config_candidates if p.exists()), None)
    if boot_config:
        text = boot_config.read_text(encoding="utf-8", errors="replace")
        additions = []
        active_lines = {line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")}
        if "dtparam=i2c_arm=on" not in active_lines:
            additions.append("dtparam=i2c_arm=on")
        if "dtoverlay=i2c-rtc,pcf8563" not in active_lines:
            additions.append("dtoverlay=i2c-rtc,pcf8563")
        if additions:
            with boot_config.open("a", encoding="utf-8") as handle:
                handle.write("\n# Added by pictl\n" + "\n".join(additions) + "\n")
            print(f"已在 {boot_config} 启用 I²C 和 PCF8563（重启后生效）。")
    run(["modprobe", "rtc-pcf8563"])
    print("PCF8563 设置完成。可用 `pictl rtc read` 检查；首次启用 I²C 后请重启。")


def _bcd(value):
    return (value // 10) << 4 | value % 10


def _unbcd(value):
    return (value >> 4) * 10 + (value & 0x0F)


def rtc_write():
    from smbus2 import SMBus
    now = datetime.datetime.now(datetime.timezone.utc)
    data = [_bcd(now.second), _bcd(now.minute), _bcd(now.hour),
            _bcd(now.day), _bcd(now.weekday()), _bcd(now.month),
            _bcd(now.year % 100)]
    with SMBus(int(load_config()["I2C_BUS"], 0), force=True) as bus:
        bus.write_i2c_block_data(0x51, 0x02, data)


def rtc_read():
    from smbus2 import SMBus
    with SMBus(int(load_config()["I2C_BUS"], 0), force=True) as bus:
        data = bus.read_i2c_block_data(0x51, 0x02, 7)
    year = 2000 + _unbcd(data[6] & 0xFF)
    value = datetime.datetime(year, _unbcd(data[5] & 0x1F),
                              _unbcd(data[3] & 0x3F), _unbcd(data[2] & 0x3F),
                              _unbcd(data[1] & 0x7F), _unbcd(data[0] & 0x7F),
                              tzinfo=datetime.timezone.utc)
    return value


def time_command(action):
    cfg = load_config()
    if action == "status":
        run(["timedatectl", "status"], check=True)
        return
    require_root()
    if action == "setup":
        run(["timedatectl", "set-timezone", cfg["TIMEZONE"]], check=True)
        run(["timedatectl", "set-ntp", "true"], check=True)
        rtc_setup()
        run(["systemctl", "disable", "pictl-time-sync.service"])
        run(["systemctl", "enable", "--now", "pictl-time-sync.timer"], check=True)
        print(f"时区已设为 {cfg['TIMEZONE']}，网络校时和 RTC 自动同步已启用。")
        return
    result = subprocess.run(
        ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    if result.stdout.strip().lower() != "yes":
        raise RuntimeError("网络时间尚未同步，定时器稍后会自动重试。")
    rtc_write()
    print("网络时间已同步并写入 PCF8563。")


def configure():
    require_root()
    cfg = load_config()
    labels = {
        "FAN_GPIO": "风扇 BCM GPIO",
        "FAN_ON_TEMP": "开启温度 °C",
        "FAN_OFF_TEMP": "关闭温度 °C",
        "I2C_BUS": "I²C 总线",
        "BATTERY_ADDRESS": "电量芯片地址",
        "BATTERY_REGISTER": "电量寄存器",
        "BATTERY_LOW": "低电量阈值 %",
        "BATTERY_AUTO_SHUTDOWN": "低电量自动关机（1/0）",
        "OLED_ADDRESS": "OLED I²C 地址",
        "OLED_WIDTH": "OLED 宽度",
        "OLED_HEIGHT": "OLED 高度",
        "OLED_ROTATE": "OLED 旋转（0/180）",
        "OLED_PAGE_SECONDS": "OLED 换页秒数",
        "TIMEZONE": "系统时区",
    }
    print("直接回车保留当前值。")
    for key in DEFAULTS:
        value = input(f"{labels[key]} [{cfg[key]}]: ").strip()
        if value:
            cfg[key] = value
    if float(cfg["FAN_OFF_TEMP"]) >= float(cfg["FAN_ON_TEMP"]):
        raise SystemExit("关闭温度必须小于开启温度，配置未保存。")
    CONFIG.write_text("".join(f"{key}={cfg[key]}\n" for key in DEFAULTS), encoding="utf-8")
    run(["systemctl", "try-restart", "pictl-fan.service"])
    print("配置已保存。")


def status():
    cfg = load_config()
    try:
        temp = f"{temperature():.1f} °C"
    except Exception as exc:
        temp = str(exc)
    print(f"CPU 温度：{temp}")
    print(f"风扇服务：{service_active('pictl-fan.service')}")
    print(f"电量服务：{service_active('pictl-battery.service')}")
    print(f"OLED 服务：{service_active('pictl-display.service')}")
    print(f"风扇配置：BCM {cfg['FAN_GPIO']}，{cfg['FAN_ON_TEMP']}°C 开 / {cfg['FAN_OFF_TEMP']}°C 关")
    print(f"电量配置：总线 {cfg['I2C_BUS']}，地址 {cfg['BATTERY_ADDRESS']}，寄存器 {cfg['BATTERY_REGISTER']}")


def uninstall():
    require_root()
    for unit in ("pictl-fan.service", "pictl-battery.service", "pictl-display.service", "pictl-time-sync.service", "pictl-time-sync.timer"):
        run(["systemctl", "disable", "--now", unit])
        Path("/etc/systemd/system", unit).unlink(missing_ok=True)
    run(["systemctl", "daemon-reload"])
    Path("/usr/local/bin/pictl").unlink(missing_ok=True)
    Path("/usr/bin/pictl").unlink(missing_ok=True)
    shutil.rmtree("/usr/local/lib/pictl", ignore_errors=True)
    print("程序已卸载；配置 /etc/pictl.conf 已保留。")


def menu():
    actions = {
        "1": lambda: status(),
        "2": lambda: print(f"CPU 温度：{temperature():.1f} °C"),
        "3": lambda: fan_command("auto"),
        "4": lambda: fan_command("on"),
        "5": lambda: fan_command("off"),
        "6": lambda: print(f"电量：{battery_value()}%"),
        "7": configure,
        "8": rtc_setup,
        "9": lambda: display_command("on"),
    }
    while True:
        print("\n树莓派简易管理\n1 状态  2 温度  3 自动风扇  4 风扇开  5 风扇关\n6 电量  7 设置  8 配置时钟  9 开启OLED  0 退出")
        choice = input("请选择：").strip()
        if choice == "0":
            return
        try:
            actions.get(choice, lambda: print("无效选项。"))()
        except Exception as exc:
            print(f"操作失败：{exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="树莓派风扇、RTC 和电量管理工具")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("menu")
    sub.add_parser("status")
    sub.add_parser("temp")
    sub.add_parser("config")
    sub.add_parser("uninstall")
    fan = sub.add_parser("fan")
    fan.add_argument("mode", choices=("auto", "on", "off"))
    rtc = sub.add_parser("rtc")
    rtc.add_argument("action", choices=("setup", "read", "system-to-rtc", "rtc-to-system"))
    battery = sub.add_parser("battery")
    battery.add_argument("action", nargs="?", choices=("read", "enable", "disable"), default="read")
    sub.add_parser("fan-daemon", help=argparse.SUPPRESS)
    sub.add_parser("battery-daemon", help=argparse.SUPPRESS)
    clock = sub.add_parser("time")
    clock.add_argument("action", nargs="?", choices=("setup", "sync", "status"), default="status")
    display = sub.add_parser("display")
    display.add_argument("action", nargs="?", choices=("on", "off", "test", "status"), default="status")
    sub.add_parser("display-daemon", help=argparse.SUPPRESS)
    args = parser.parse_args()
    command = args.command or "menu"
    if command == "menu": menu()
    elif command == "status": status()
    elif command == "temp": print(f"{temperature():.1f} °C")
    elif command == "config": configure()
    elif command == "fan": fan_command(args.mode)
    elif command == "fan-daemon": fan_daemon(args)
    elif command == "battery-daemon": battery_daemon(args)
    elif command == "display-daemon": display_daemon(args)
    elif command == "display": display_command(args.action)
    elif command == "time": time_command(args.action)
    elif command == "battery":
        if args.action == "read": print(f"{battery_value()}%")
        else:
            service("pictl-battery.service", "enable" if args.action == "enable" else "disable")
            service("pictl-battery.service", "start" if args.action == "enable" else "stop")
            print("电量监控服务已启用。" if args.action == "enable" else "电量监控服务已停用。")
    elif command == "rtc":
        if args.action == "setup": rtc_setup()
        elif args.action == "read":
            print(rtc_read().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"))
        elif args.action == "system-to-rtc":
            require_root()
            rtc_write()
            print("系统时间已写入 PCF8563。")
        else:
            require_root()
            value = rtc_read()
            run(["date", "-u", "-s", value.strftime("%Y-%m-%d %H:%M:%S")], check=True)
    elif command == "uninstall": uninstall()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        raise SystemExit(f"错误：{exc}")
