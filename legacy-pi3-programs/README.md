# Raspberry Pi 3 legacy program backup

[中文说明](#中文说明)

This directory is a read-only backup copied from a working Raspberry Pi 3B+. The source device runs Raspbian 9 Stretch, Python 2.7.13, and Python 3.5.3.

## Active programs

- `Adafruit_Python_SSD1306/examples/stats.py`: active SSD1306 128×32 OLED program. It displays the IP address, CPU load, memory usage, and disk usage.
- `startup/fan.py`: active temperature-controlled fan program using BCM GPIO 13. It switches on above 50°C and off below 39°C.
- `startup/rc.local`: original boot configuration that starts both programs.

## Archived programs and notes

- `startup/fan1.py`: older fan-control variant.
- `pi/PI4的电池bat显示.py`: old I²C battery reader for address `0x66`; it is not currently started at boot.
- `pi/`: original OLED, RTC, fan, GPIO, key, and battery notes copied from the desktop.
- `Adafruit_Python_SSD1306/`: complete legacy Adafruit SSD1306 library, examples, build output, and original license.

The files are preserved as found. They are intended for backup and historical reference; no modernization or behavioral changes have been applied.

## 中文说明

这个目录是从正在工作的 Raspberry Pi 3B+ 原样下载的旧程序备份。源设备使用 Raspbian 9 Stretch、Python 2.7.13 和 Python 3.5.3。

### 当前正在运行

- `Adafruit_Python_SSD1306/examples/stats.py`：SSD1306 128×32 OLED 显示程序，显示 IP、CPU 负载、内存和磁盘。
- `startup/fan.py`：BCM GPIO 13 温控风扇，高于 50°C 开启，低于 39°C 关闭。
- `startup/rc.local`：原始开机启动配置，负责启动 OLED 和风扇程序。

### 其他备份

- `startup/fan1.py`：较早的风扇控制版本。
- `pi/PI4的电池bat显示.py`：I²C 地址 `0x66` 的旧电池读取程序，目前没有开机运行。
- `pi/`：桌面中保存的 OLED、RTC、风扇、GPIO、按键和电池笔记。
- `Adafruit_Python_SSD1306/`：完整旧版 Adafruit SSD1306 库、示例、构建文件和原始许可证。

所有文件均按 Pi 上的原始状态保存，没有修改运行逻辑。
