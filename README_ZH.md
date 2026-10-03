# Raspberry Pi 简易管理工具

[English documentation](README.md)

把旧笔记中的温控风扇、PCF8563 时钟和 I²C 电量检测整理成一个工具。

支持使用 `apt` 和 systemd 的树莓派发行版：

- Raspberry Pi OS（32/64 位）
- Ubuntu for Raspberry Pi
- Kali Linux ARM
- 其他基于 Debian/Ubuntu 的树莓派系统

安装器会检测树莓派硬件，并在软件源提供时自动安装 `lgpio`，兼容较新的树莓派型号。

完整接线、安装、操作和排错方法请参阅 [使用说明.md](使用说明.md)。

## 一键完整安装

在 Raspberry Pi OS、Ubuntu for Raspberry Pi 或 Kali ARM 中执行：

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/XXboard/raspberry-pi-pictl.git
cd raspberry-pi-pictl
sudo bash install.sh --full
sudo reboot
```

`--full` 会一次完成：

- 安装 Python、GPIO、I²C 和 OLED 依赖
- 安装 `pictl` 中文管理命令
- 启用 60°C 开、39°C 关的温控风扇
- 启用 SSD1306 OLED 两行轮播
- 启用电量曲线记录和 5% 自动安全关机
- 设置 `Asia/Shanghai` 中国时区
- 启用 PCF8563 和网络自动校时
- 设置全部 systemd 开机服务

> 默认硬件参数为风扇 BCM GPIO 13、OLED `0x3C`（128×32）、PCF8563 `0x51`、电量芯片 `0x66`。硬件不同请在安装后运行 `sudo pictl config` 修改。

## 基础安装

```bash
chmod +x install.sh
sudo ./install.sh
```

安装后直接运行中文菜单：

```bash
sudo pictl
```

常用命令：

```bash
pictl status                 # 查看状态
pictl temp                   # 查看 CPU 温度
sudo pictl fan auto          # 温控模式
sudo pictl fan on            # 强制开启
sudo pictl fan off           # 强制关闭
sudo pictl config            # 修改 GPIO、温度和 I²C 参数
sudo pictl rtc setup         # 配置 PCF8563（启用 I²C）
pictl rtc read               # 读取硬件时钟
pictl battery                # 读取一次电量
sudo pictl battery enable    # 启用电量监控服务
sudo pictl display on        # 启用 SSD1306 OLED 状态显示
sudo pictl display test      # 发送一次测试画面
sudo pictl time setup        # 设置中国时区、网络校时和 RTC 自动同步
pictl time status            # 查看时间同步状态
sudo pictl uninstall         # 卸载
```

配置保存在 `/etc/pictl.conf`。默认使用 BCM GPIO 13；风扇高于 60°C 开启，低于 39°C 关闭。OLED 默认使用 I²C 地址 `0x3c`、128×32 分辨率（原 Adafruit `stats.py` 的默认型号），并以两行大字每 3 秒轮播时间/日期、温度/风扇和电量/IP；分辨率及换页时间可通过 `sudo pictl config` 修改。

电量监控每次循环（约每 3 秒）都保存一条读数到 `/var/lib/pictl/battery.csv`。OLED 不再显示曲线。电量必须连续保持 100% 至少 3 分钟才确认充满，短暂跳到 100% 不会重置计时；保持满电时使用时间为零，开始掉电后从最后一条 100% 记录重新计时。旧周期记录仍会保留。连续三次检测到 0% 时自动安全关机。

## 注意

- 面向带 GPIO 的 Raspberry Pi 和 Debian/Kali/Raspberry Pi OS。
- 风扇控制脚必须经过合适的三极管/MOSFET 驱动，不要直接用 GPIO 给风扇供电。
- 电量芯片因原项目没有留下芯片型号和寄存器定义，默认按 I²C 总线 1、地址 `0x66`、寄存器 `0x01` 读取 0–100。可在 `sudo pictl config` 中修改。
- PCF8563 使用 Linux 内核的 `rtc-pcf8563` 驱动，不再下载旧 Python 仓库。
