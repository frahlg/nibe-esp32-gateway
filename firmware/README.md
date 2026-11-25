# Firmware

Firmware is the next step of this project. This folder holds the pin map and a
starting configuration, so the hardware and the software agree from day one.

## Pin map (hardware rev 1.0)

| ESP32-S3 pin | Net | Use |
|---|---|---|
| GPIO9 | RS485_TX | UART TX to THVD1450 DI |
| GPIO12 | RS485_RX | UART RX from THVD1450 RO (10 kΩ pull-up) |
| GPIO10 | RS485_DE | Driver enable, wired to DE and /RE. High = transmit. 10 kΩ pull-down, so the board only listens after reset |
| GPIO38 | LED_STAT | Green STAT LED, active high |
| GPIO39 | LED_BUS | White BUS LED, active high |
| GPIO0 | BOOT | BOOT button, low at reset = download mode |
| EN | EN | RESET button |
| GPIO19 / GPIO20 | USB D- / D+ | Native USB (USB Serial/JTAG) on the USB-C socket |
| GPIO1, GPIO2 | EXP_IO1/2 | Spare, on header J3 (not fitted) |
| GPIO43 / GPIO44 | TXD0 / RXD0 | UART0, on header J3 |

The bus runs at 9600 baud, 8 data bits, no parity, 1 stop bit. See
[../docs/protocol.md](../docs/protocol.md).

## First flash

A new board has an empty flash, so the ROM boot loader needs the BOOT button
once:

1. Hold BOOT, plug in USB-C, release BOOT.
2. Flash with ESPHome (`esphome run nibe-gateway.yaml`) or `esptool.py`.

After that, flash over USB without buttons, or over Wi-Fi (OTA).

## Starting configuration

[nibe-gateway.yaml](nibe-gateway.yaml) uses the
[esphome-nibe](https://github.com/elupus/esphome-nibe) component (NibeGW). It
answers the heat pump and forwards the data over UDP to the Home Assistant
[Nibe Heat Pump](https://www.home-assistant.io/integrations/nibe_heatpump/)
integration. It has not run on this board yet.

Two things from the community matter for the firmware:

- The heat pump expects a reply within a short time. Heavy logging or long
  blocking work in the main loop makes replies late, and the pump then raises
  alarm 251. Keep logging at WARN in normal use.
- Some users saw late replies under ESPHome on some boards, and fixed them with
  the native ESP-IDF gateway [nibegw-esp](https://github.com/nptr/nibegw-esp).
  That project drives DE from the UART's RTS line, which works with GPIO10 on
  this board too.
