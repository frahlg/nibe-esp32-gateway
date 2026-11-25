# Firmware

The gateway runs [ESPHome](https://esphome.io) with the
[esphome-nibe](https://github.com/elupus/esphome-nibe) NibeGW component. It
answers the heat pump on the bus the way a MODBUS 40 does, and passes the data
to Home Assistant's [Nibe Heat Pump](https://www.home-assistant.io/integrations/nibe_heatpump/)
integration over UDP on your local network. Nothing goes to the cloud.

[`nibe-gateway.yaml`](nibe-gateway.yaml) is a "factory" configuration: it has no
Wi-Fi password in it, so the same image works for everyone. You set up Wi-Fi
after flashing.

> **Status:** the firmware compiles (ESPHome 2026.11.1: 30 % of RAM, 22 % of
> flash) and the bench tester's own tests pass. It has not run on a real board
> or heat pump yet.

## What the LEDs mean

| LED | Meaning |
|---|---|
| PWR (red) | The board has power |
| STAT (green) | Steady: Wi-Fi is up. Blinking: no Wi-Fi yet (set-up mode) |
| BUS (white) | Blinks once for every data telegram from the heat pump |

## 1. Build

You need Docker, or ESPHome installed with `pip`/`uv`.

```bash
cd firmware
docker run --rm -v "$PWD":/config -v esphome-cache:/cache esphome/esphome:2026.11.1 compile nibe-gateway.yaml
```

The image to flash is `.esphome/build/nibe-gateway/build/firmware.factory.bin`.
The first build downloads the ESP-IDF tools (about 2 GB, kept in the
`esphome-cache` volume).

## 2. First flash

A new board has an empty flash, so the ESP32-S3 needs the BOOT button once:

1. Hold **BOOT**, plug in USB-C, release **BOOT**.
2. Flash it, one of these ways:
   - In Chrome or Edge, open <https://web.esphome.io>, click **Connect**, pick
     the port, click **Install** and choose `firmware.factory.bin`.
   - Or from the command line: `esphome run nibe-gateway.yaml` (or the Docker
     command above with `run` in place of `compile`, adding `--device` for the
     USB port on Linux).
3. Press **RESET**, or unplug and plug in again.

After this you never need the buttons again: later updates go over Wi-Fi (OTA)
or over USB-C.

## 3. Set up Wi-Fi

Pick one:

- **From a phone.** Join the Wi-Fi network **NIBE Gateway Setup**. A page opens
  (or browse to <http://192.168.4.1>); choose your network and enter the
  password.
- **Over USB.** On <https://web.esphome.io>, connect and click **Configure
  Wi-Fi** (this uses [Improv](https://www.improv-wifi.com)).

The STAT LED goes steady when the gateway is on your network. It shows a status
page at `http://nibe-gateway-xxxxxx.local` (the last six characters come from
the board's MAC address).

## 4. Home Assistant

1. **ESPHome:** Home Assistant finds the gateway on its own. Add it under
   *Settings → Devices & services*. If you use the ESPHome add-on, you can also
   *Adopt* it there and change the configuration later.
2. **Nibe Heat Pump:** add the integration, choose **NibeGW** and fill in:

   | Field | Value |
   |---|---|
   | Model | F750 (or yours) |
   | IP address | the gateway's IP |
   | Remote read port | 9999 |
   | Remote write port | 10000 |
   | Listening port | 9999 |

   The gateway sends the pump's data to whoever sends it valid requests, so no
   address needs to be set in the firmware.

## 5. Test on the bench first

No board yet? The same firmware runs on an ESP32-S3-DevKitC-1 with an RS-485
module; see [../docs/test-rig.md](../docs/test-rig.md).

Before you connect the gateway to the heat pump, check it with a cheap USB-RS485
adapter (CH340 or FT232 with a MAX485, about USD 3). The tester in
[`../tools/pump_simulator.py`](../tools/pump_simulator.py) plays the heat pump:
it sends data telegrams, read and write tokens and the accessory version
request, checks each reply, measures how fast the gateway answers, and applies
the pump's alarm rule.

1. Wire the adapter's A, B and GND to the gateway's A, B and GND terminals. Leave
   12V empty and power the gateway from USB-C.
2. Run:

   ```bash
   uv run tools/pump_simulator.py --port /dev/tty.usbserial-XXXX --duration 60
   ```

   Add `--gateway-ip <gateway IP>` to also test the Home Assistant side: the
   tester then sends read and write requests over UDP and checks that they reach
   the bus and that the answers come back.
3. It ends with `RESULT: PASS` or `RESULT: FAIL` and a summary: replies,
   NAKs, timeouts, reply times (median, 95th percentile, max) and whether the
   alarm would have fired.

If replies are slow (the tester flags anything over 100 ms) or missing, fix that
before you go near the pump. The tester's own tests run without hardware:

```bash
uv run --with pyserial --with pytest pytest -p no:cacheprovider tools -q
```

## 6. Connect to the heat pump

Follow [../docs/installation.md](../docs/installation.md). Only tick MODBUS 40
in the pump's service menu once the gateway passes the bench test. From then on
the pump expects an answer to every telegram: if the gateway is silent for about
15 seconds the pump raises **alarm 251** and blocks the accessory until someone
resets the alarm. If you take the gateway away, untick MODBUS 40 first.

Keep the logger at INFO or lower in normal use. Heavy logging slows the replies
to the pump, a known cause of alarm 251.

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

## If ESPHome is too slow

Some users saw late replies under ESPHome on other boards. If the bench test
shows that, the native ESP-IDF gateway [nibegw-esp](https://github.com/nptr/nibegw-esp)
is the fallback. It drives DE from the UART's RTS line, which works with GPIO10
on this board.
