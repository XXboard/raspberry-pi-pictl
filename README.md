# Raspberry Pi PiCtl

[中文说明](README_ZH.md)

PiCtl is a lightweight Raspberry Pi management utility for a temperature-controlled fan, SSD1306 OLED status display, PCF8563 real-time clock, and an I²C battery gauge.

## Supported systems

- Raspberry Pi OS, 32-bit or 64-bit
- Ubuntu for Raspberry Pi
- Kali Linux ARM
- Other Raspberry Pi distributions based on Debian or Ubuntu with `apt` and systemd

The installer detects Raspberry Pi hardware and installs the `lgpio` backend when it is available, improving compatibility with newer Raspberry Pi boards.

## Default hardware configuration

| Device | Default setting |
|---|---|
| Fan | BCM GPIO 13 |
| Fan start temperature | 60°C |
| Fan stop temperature | 39°C |
| SSD1306 OLED | I²C `0x3C`, 128×32 |
| PCF8563 RTC | I²C `0x51` |
| Battery gauge | I²C `0x66`, register `0x01` |
| Low-battery shutdown | 5% after three consecutive readings |
| Time zone | `Asia/Shanghai` |

> Do not power a fan directly from a GPIO pin. Use a suitable transistor or MOSFET driver and a correctly rated power supply.

## One-command full installation

Run the following on your Raspberry Pi:

```bash
sudo apt update && sudo apt install -y git && \
git clone https://github.com/XXboard/raspberry-pi-pictl.git && \
cd raspberry-pi-pictl && \
sudo bash install.sh --full && \
sudo reboot
```

The `--full` option installs dependencies and configures:

- The `pictl` command and Chinese interactive menu
- Automatic temperature-controlled fan operation
- A two-line rotating SSD1306 OLED status display
- Battery logging and a battery-versus-time graph
- Safe automatic shutdown at 5%
- PCF8563 RTC support
- Network time synchronization
- Automatic startup through systemd

## Basic installation

If you only want to install the software and fan service:

```bash
git clone https://github.com/XXboard/raspberry-pi-pictl.git
cd raspberry-pi-pictl
sudo bash install.sh
```

## Common commands

Open the interactive menu:

```bash
sudo pictl
```

Check all services and settings:

```bash
pictl status
```

### Fan

```bash
sudo pictl fan auto    # Temperature-controlled mode
sudo pictl fan on      # Force on
sudo pictl fan off     # Force off
pictl temp             # Show CPU temperature
```

The default hysteresis is 60°C on and 39°C off. Between these temperatures, the previous fan state is retained to prevent rapid switching.

### OLED display

```bash
sudo pictl display on
sudo pictl display off
sudo pictl display test
pictl display status
```

The default 128×32 display rotates through two-line pages containing:

- Time and date
- CPU temperature and fan mode
- Battery percentage and elapsed runtime
- IP address
- Battery-versus-time graph

### Battery monitoring

```bash
pictl battery
sudo pictl battery enable
sudo pictl battery disable
```

The monitor averages ten readings and appends a sample approximately every 30 seconds to:

```text
/var/lib/pictl/battery.csv
```

The data survives reboot because it is stored on the SD card. When three consecutive averaged readings are at or below 5%, PiCtl performs a safe system shutdown.

### Time and PCF8563 RTC

```bash
sudo pictl time setup
pictl time status
pictl rtc read
sudo pictl rtc system-to-rtc
sudo pictl rtc rtc-to-system
```

The time synchronization timer checks periodically. After network time has synchronized, it writes the correct UTC time to the PCF8563.

## Configuration

Run:

```bash
sudo pictl config
```

Press Enter to keep the current value. Settings are stored in:

```text
/etc/pictl.conf
```

After changing fan or display settings, restart the relevant services:

```bash
sudo systemctl restart pictl-fan.service
sudo systemctl restart pictl-display.service
```

## Checking I²C devices

```bash
sudo modprobe i2c-dev
sudo i2cdetect -y 1
```

Expected addresses for the default hardware are:

- `3C`: SSD1306 OLED
- `51` or `UU`: PCF8563 RTC
- `66`: Battery gauge

## Service status and logs

```bash
systemctl status pictl-fan.service
systemctl status pictl-display.service
systemctl status pictl-battery.service
systemctl status pictl-time-sync.timer
```

To inspect recent errors:

```bash
journalctl -u pictl-fan.service -n 50 --no-pager
journalctl -u pictl-display.service -n 50 --no-pager
journalctl -u pictl-battery.service -n 50 --no-pager
```

## Troubleshooting

### OLED does not display anything

1. Check VCC, GND, SDA, and SCL wiring.
2. Confirm that `sudo i2cdetect -y 1` shows address `0x3C`.
3. Run `sudo pictl display test`.
4. If the display is 128×64, run `sudo pictl config`, change the OLED height to `64`, and restart `pictl-display.service`.

### OLED is upside down

Run `sudo pictl config`, change OLED rotation to `180`, then restart the display service.

### Fan does not run

Check the BCM GPIO number, driver transistor or MOSFET, fan power supply, and ground connection. Test with:

```bash
sudo pictl fan on
```

### Time is incorrect

```bash
sudo pictl time setup
pictl time status
sudo pictl rtc system-to-rtc
```

## Updating

```bash
cd ~/raspberry-pi-pictl
git pull
sudo bash install.sh --full
sudo reboot
```

The existing `/etc/pictl.conf` file is preserved during reinstallation.

## Uninstalling

```bash
sudo pictl uninstall
```

PiCtl stops and removes its services and program files. `/etc/pictl.conf` is retained so that settings can be reused after a future installation.
