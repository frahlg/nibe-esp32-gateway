# The NIBE accessory bus (MODBUS 40 port)

This is a summary of what the open-source community has worked out about the
bus between a NIBE F-series heat pump and its MODBUS 40 accessory. NIBE does not
publish this protocol. Sources are at the end; facts we could not confirm are
marked as such.

## Physical layer

| Item | Value |
|---|---|
| Interface | RS-485, two wires (A, B) plus ground |
| Serial format | 9600 baud, 8 data bits, no parity, 1 stop bit |
| Bus master | The heat pump. Once the accessory is enabled it sends on its own; the accessory only answers |
| Power | The pump supplies 12 V on the same terminal. MODBUS 40 is rated 12 V DC, 45–80 mA, and runs from it |
| Polarity | NIBE's convention is A = +, B = − |

### Where the bus is on the heat pump

| Model | Terminal | 12 V | A | B | GND |
|---|---|---|---|---|---|
| F750, F730, F470, F370 | AA3-X4 | 12 | 11 | 10 | 9 |
| F1145, F1155, F1245, F1255 | AA3-X4 | 12 | 11 | 10 | 9 |
| SMO 40, VVM 225/310/320/325/500 | AA3-X4 | 12 | 11 | 10 | 9 |
| F1345 v1.0 | X6 | pins 4–7, order in the MODBUS 40 manual | | | |
| F1345 2.0, F1355 | AA101-X10 | 7 | 8 | 9 | 10 |

The F750 installer manual's own wiring sheet labels AA3-X4 differently (only
13/14/15 carry the names GND/B/A). Every MODBUS 40 manual uses 9–12, and so do
working community installs. Use 9–12.

How much current X4:12 can supply is not published. Known loads that work:
MODBUS 40 (up to 80 mA), a LilyGo T-CAN485 ESP32 board, a custom ESP32-C6 board
(about 40 mA at 12 V) and NibePi (a Raspberry Pi Zero). We estimate this board
draws about 40 mA at 12 V on average, with short peaks near 120 mA when Wi-Fi
transmits (not measured yet).

### Termination and bias

NIBE does not say whether the pump terminates or biases the bus. The reference
board for the esphome-nibe project (LilyGo T-CAN485) has a fixed 120 Ω
terminator and 4.7 kΩ bias resistors, and it works on many pumps. This board
copies that, with the terminator on a solder jumper you can cut.

## Frames

All multi-byte numbers are little endian.

**Pump to accessory**

```
5C  ADDR_H  ADDR_L  CMD  LEN  DATA[LEN]  CHK
```

- `ADDR` is the accessory address. MODBUS 40 is `0x0020`, SMS 40 is `0x0016`,
  RMU 40 S1–S4 are `0x19`–`0x1C`.
- `CHK` is the XOR of every byte from `ADDR_H` to the end of `DATA`. The start
  byte is left out.
- A data byte `0x5C` is sent twice (`5C 5C`). `LEN` and `CHK` cover the bytes as
  sent. Remove the duplicates after you check the frame.

**Accessory to pump**

```
C0  CMD  LEN  DATA[LEN]  CHK
```

- `CHK` is the XOR of every byte from `C0` to the end of `DATA`.
- If the XOR comes out as `0x5C`, the sender puts `0xC5` instead.

**Single bytes:** `06` = ACK, `15` = NAK (checksum error).

## Commands

| CMD | Name | What happens |
|---|---|---|
| `68` | Data | The pump pushes up to 20 registers from LOG.SET, as pairs of u16 address and u16 value. The accessory ACKs. |
| `69` | Read token | Empty frame. The accessory answers ACK, or asks for one register: `C0 69 02 <reg> CHK`. The pump ACKs. |
| `6A` | Read response | u16 register plus 4 value bytes. The accessory answers ACK or NAK. |
| `6B` | Write token | Empty frame. The accessory answers ACK, or writes one register: `C0 6B 06 <reg> <4 bytes> CHK`. |
| `6C` | Write result | 1 byte, 1 = written. The accessory ACKs. |
| `6D` | Product info | Version and model name. |
| `6E` | Modbus address message | |
| `EE` | Accessory version request | esphome-nibe answers `C0 EE 03 0A 00 01` (plus CHK) as a fixed reply. |
| `60`, `62`, `63` | RMU 40 commands | Used to emulate a room unit. |

Examples from the community:

```
pump:       5C 00 20 69 00 49          read token
accessory:  C0 69 02 24 AC 23          read register 0xAC24
pump:       06

pump:       5C 00 20 6A 07 73 B0 5C 5C 00 00 00 8E
            (read response with an escaped 5C byte)
```

## Timing

The accessory must answer every telegram. If the pump hears nothing for about
15 s it raises **alarm 251, "Com. fault acc. MODBUS"**, blocks the accessory, and
the alarm needs a manual reset.

NIBE publishes no reply deadline (not confirmed). What the community found:

- Replies more than about 100 ms late collide with the next frames and cause
  alarms.
- Debug logging and long blocking code in the main loop make replies late.
- esphome-nibe waits 1 ms before and after each transmit when it drives the DE
  pin.

## Enabling the accessory in the pump

1. On the F750, hold Back for 7 s to open the service menu.
2. Open menu 5.2 "system settings" (5.2.4 "accessories" on some models and
   firmware versions) and tick MODBUS 40. Which of the two your F750 shows
   depends on its firmware (not confirmed).
3. The pump needs firmware newer than 3000.

If you take the gateway away later, untick MODBUS 40 first, or the pump goes
into alarm.

## LOG.SET

LOG.SET is a file that picks the 20 registers the pump pushes with command
`68`. It is **optional**: without it the telegrams still arrive, only empty,
and the gateway can still read any register with the read token.

- Make it with NIBE ModbusManager (Windows), `nibe-cli log-set`
  ([nibe library](https://github.com/yozik04/nibe)) or a script.
- Load it: copy LOG.SET to a USB stick, put the stick in the display unit
  (the USB socket is behind the badge with the model name), open menu USB →
  logging, tick "activated", wait 15 s, remove the stick.

## Sources

NIBE documents
- MODBUS 40 installer manual IHB 1822-10: https://professional.nibe.eu/document/Installer%20manual%20(IHB)/031725-10.pdf
- MODBUS 40 installer manual IHB 1417-5: https://www.taloon.com/media/attachments/nibe/tiedonsiirtomoduuli_nibe_modbus_40_asennusohje.pdf
- F750 installer manual IHB EN 2218-2: https://assetstore.nibe.se/hcms/v2.3/entity/document/330615/storage/MzMwNjE1LzAvbWFzdGVy
- F750 service manual SEM EN 1726-2: https://assetstore.nibe.se/hcms/v2.3/entity/document/33899/storage/MDMzODk5LzAvbWFzdGVy
- NIBE FAQ MODBUS 40: https://headless.nibe.eu/download/18.3bd9d98318c457ffd81167a/1703680919388/Modubs40%20eng-1321.pdf
- NIBE FAQ LOG.SET: https://headless.nibe.eu/download/18.9a97aba184a9b5f272c5c/1669796068500/DOH%2014-262-36%20FAQ%20LogSet%201722-3.pdf
- NIBE NL, MODBUS 40 and building management: https://www.nibe.eu/download/18.21edef14198b71b09193d9/1755699289266/Modbus%2040%20koppeling%20en%20mogelijkheden%20m.b.t.%20het%20gbs.pdf

Open-source projects
- esphome-nibe: https://github.com/elupus/esphome-nibe (README, `components/nibegw`, issues 14, 21, 46, 99, 108, 152, 165, 171)
- openHAB NibeGW: https://github.com/openhab/openhab-addons/tree/main/bundles/org.openhab.binding.nibeheatpump/contrib/NibeGW
- nibegw-esp: https://github.com/nptr/nibegw-esp (`main/nibe_protocol.h`)
- NibePi: https://github.com/anerdins/nibepi
- nibe Python library: https://github.com/yozik04/nibe
- Home Assistant integration: https://www.home-assistant.io/integrations/nibe_heatpump/
- LilyGo T-CAN485 schematic: https://github.com/Xinyuan-LilyGO/T-CAN485
- Waveshare-based adapter notes: https://github.com/beolink/Nibe-F-series-ModbusAdapter
