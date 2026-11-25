"""The circuit: every part, its nets, where it sits on the schematic and on the board.

This file is the single source of truth. build.py turns it into a KiCad
schematic and board and checks both with KiCad's own ERC and DRC.

Board coordinates are millimetres from the top-left corner of the board,
y pointing down (KiCad convention). The ESP32 antenna sits at the top edge,
the NIBE terminal at the bottom edge and the USB-C socket on the left edge.
"""
from parts import P, R0603, C0603, C0805

PROJECT = "nibe-esp32-gateway"
TITLE = "NIBE ESP32 Gateway"
REV = "1.0"
DATE = "2026-11-25"

BOARD_W, BOARD_H = 50.0, 58.0

# ESP32-S3 module centre on the board (antenna flush with the top edge)
MOD_X, MOD_Y = 28.0, 12.75

NC = None


def r0603(value):
    return ("Device:R", "Resistor_SMD:R_0603_1608Metric", value, R0603[value], "")


def c0603(value):
    return ("Device:C", "Capacitor_SMD:C_0603_1608Metric", value, C0603[value], "")


def c0805(value):
    return ("Device:C", "Capacitor_SMD:C_0805_2012Metric", value, C0805[value], "")


FERRITE = ("Device:FerriteBead", "Inductor_SMD:L_0805_2012Metric", "220R@100MHz 3A", "C76818", "MPZ2012S221AT000")
TVS18 = ("Diode:SMAJ18A", "Diode_SMD:D_SMA", "SMAJ18A", "C118306", "SMAJ18A/TR13")
JP_BRIDGED = ("Jumper:SolderJumper_2_Bridged", "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm",
              "TERM", "", "")

# --------------------------------------------------------------------------------------
# Parts: ref -> (part tuple, nets{pin: net}, schematic (x, y, rot), board (x, y, rot), extra)
# --------------------------------------------------------------------------------------
PARTS = {}


def add(ref, part, nets, sch, pcb, **kw):
    PARTS[ref] = dict(part=part, nets=nets, sch=sch, pcb=pcb, **kw)


# ---------------- power input ----------------------------------------------------------
add("J1", P["USBC"], {
    "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
    "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
    "A5": "CC1", "B5": "CC2",
    "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
    "A8": NC, "B8": NC,
}, sch=(40.64, 88.9, 0), pcb=(3.35, 23.4, 270), note="USB-C: programming and bench power")
add("R1", r0603("5.1k"), {"1": "CC1", "2": "GND"}, sch=(78.74, 96.52, 0), pcb=(10.6, 19.6, 0))
add("R2", r0603("5.1k"), {"1": "CC2", "2": "GND"}, sch=(88.9, 96.52, 0), pcb=(10.4, 27.4, 0))
add("U1", P["USBLC6"], {"1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN", "5": "VBUS", "2": "GND"},
    sch=(124.46, 91.44, 0), pcb=(13.6, 23.4, 180))
add("D1", P["B5819W"], {"2": "VBUS", "1": "VSYS"}, sch=(124.46, 50.8, 180), pcb=(3.6, 34.4, 90))

add("F1", P["PTC500"], {"1": "12V_IN", "2": "VIN"}, sch=(60.96, 35.56, 90), pcb=(16.5, 44.8, 90))
add("D3", TVS18, {"1": "VIN", "2": "GND"}, sch=(76.2, 43.18, 270), pcb=(12.5, 44.5, 270))
add("C1", c0805("10uF/25V"), {"1": "VIN", "2": "GND"}, sch=(86.36, 43.18, 0), pcb=(9.5, 44.6, 270))
add("D2", P["B5819W"], {"2": "VIN", "1": "VSYS"}, sch=(104.14, 35.56, 180), pcb=(11.0, 39.6, 0))
add("C2", c0805("10uF/25V"), {"1": "VSYS", "2": "GND"}, sch=(142.24, 43.18, 0), pcb=(3.6, 40.2, 270))
add("FB1", FERRITE, {"1": "VSYS", "2": "VBUCK"}, sch=(157.48, 35.56, 90), pcb=(7.4, 37.0, 90))

# ---------------- 3.3 V buck -----------------------------------------------------------
# RT (pin 1) is left open: the TPS62933 then switches at 500 kHz, the frequency TI
# pairs with 4.7 uH for a 3.3 V output (datasheet SLUSEA4, table 10-2). EN (pin 2)
# is open too; an internal pull-up turns the regulator on.
# U4 is turned 90 degrees: SW sits on the corner next to L1, VIN and GND face the
# input capacitors, FB faces the divider on the far side from SW.
add("U4", P["TPS62933"], {"3": "VBUCK", "2": NC, "7": "SS", "1": NC, "4": "GND",
                          "6": "BST", "5": "SW", "8": "FB"},
    sch=(175.26, 86.36, 0), pcb=(11.0, 33.0, 90))
add("C4", c0603("100nF"), {"1": "VBUCK", "2": "GND"}, sch=(154.94, 88.9, 0), pcb=(11.5, 35.3, 0))
add("C3", c0805("10uF/25V"), {"1": "VBUCK", "2": "GND"}, sch=(144.78, 88.9, 0), pcb=(11.5, 37.2, 0))
add("C8", c0603("10nF"), {"1": "SS", "2": "GND"}, sch=(157.48, 104.14, 0), pcb=(9.9, 29.9, 90))
add("C5", c0603("100nF"), {"1": "BST", "2": "SW"}, sch=(195.58, 73.66, 0), pcb=(12.25, 30.6, 0))
add("L1", P["L4u7"], {"1": "SW", "2": "+3V3"}, sch=(203.2, 86.36, 90), pcb=(16.2, 33.0, 0))
add("C6", c0805("22uF/25V"), {"1": "+3V3", "2": "GND"}, sch=(210.82, 106.68, 0), pcb=(17.7, 37.1, 270))
add("C7", c0805("22uF/25V"), {"1": "+3V3", "2": "GND"}, sch=(223.52, 106.68, 0), pcb=(15.6, 37.1, 270))
add("R3", r0603("47k"), {"1": "+3V3", "2": "FB"}, sch=(193.04, 106.68, 0), pcb=(7.2, 30.35, 270))
add("R4", r0603("15k"), {"1": "FB", "2": "GND"}, sch=(193.04, 121.92, 0), pcb=(7.9, 32.6, 180))

# Copper areas on the top layer for the two high-current switching nets, so the
# input loop (VIN pin, C4, GND pin) and the SW node stay short and wide.
# Polygons in board mm; the zone fill keeps clearance to other nets by itself.
BUCK_ZONES = {
    "SW": [(11.6, 29.95), (14.6, 29.95), (14.6, 33.1), (11.6, 33.1)],
    "VBUCK": [(11.0, 33.4), (11.45, 33.4), (11.45, 34.4), (11.3, 34.4), (11.3, 38.0), (9.8, 38.0),
              (9.8, 36.9), (6.5, 36.9), (6.5, 34.6), (11.0, 34.6)],
}
# Ground pads in the buck loops connect to the pour without thermal spokes
SOLID_GND = [("U4", "4"), ("C4", "2"), ("C3", "2"), ("C6", "2"), ("C7", "2")]

# ---------------- ESP32-S3 -------------------------------------------------------------
esp_nets = {str(n): NC for n in range(1, 42)}
esp_nets.update({
    "1": "GND", "40": "GND", "41": "GND", "2": "+3V3", "3": "EN",
    "13": "USB_DN", "14": "USB_DP",
    "17": "RS485_TX", "18": "RS485_DE", "20": "RS485_RX",
    "27": "BOOT", "31": "LED_STAT", "32": "LED_BUS",
    "39": "EXP_IO1", "38": "EXP_IO2", "37": "TXD0", "36": "RXD0",
})
add("U3", P["ESP32S3"], esp_nets, sch=(317.5, 83.82, 0), pcb=(MOD_X, MOD_Y, 0))
add("C9", c0603("10uF"), {"1": "+3V3", "2": "GND"}, sch=(355.6, 40.64, 0), pcb=(16.6, 9.6, 270))
add("C10", c0603("100nF"), {"1": "+3V3", "2": "GND"}, sch=(365.76, 40.64, 0), pcb=(14.9, 9.6, 270))
add("R5", r0603("10k"), {"1": "+3V3", "2": "EN"}, sch=(256.54, 45.72, 0), pcb=(16.9, 13.6, 270))
add("C11", c0603("1uF"), {"1": "EN", "2": "GND"}, sch=(256.54, 63.5, 0), pcb=(16.9, 16.8, 270))
add("SW1", P["BTN"], {"1": "EN", "2": "GND"}, sch=(256.54, 78.74, 0), pcb=(11.0, 14.8, 0), label="RESET")
add("R6", r0603("10k"), {"1": "+3V3", "2": "BOOT"}, sch=(363.22, 116.84, 0), pcb=(40.4, 24.0, 180))
add("SW2", P["BTN"], {"1": "BOOT", "2": "GND"}, sch=(378.46, 132.08, 0), pcb=(44.0, 33.5, 0), label="BOOT")

# ---------------- RS-485 to the heat pump ---------------------------------------------
add("J2", P["TERM4"], {"1": "12V_IN", "2": "BUS_A", "3": "BUS_B", "4": "GND"},
    sch=(40.64, 190.5, 180), pcb=(20.0, BOARD_H - 8.0, 0), note="NIBE AA3-X4: 12=12V 11=A 10=B 9=GND")
add("D4", P["SM712"], {"1": "BUS_A", "2": "BUS_B", "3": "GND"}, sch=(83.82, 205.74, 0), pcb=(25.25, 43.5, 90))
add("R9", r0603("4.7k"), {"1": "+3V3", "2": "BUS_A"}, sch=(104.14, 180.34, 0), pcb=(21.6, 37.0, 90))
add("R10", r0603("4.7k"), {"1": "BUS_B", "2": "GND"}, sch=(114.3, 220.98, 0), pcb=(29.4, 37.6, 270))
add("R11", r0603("120"), {"1": "BUS_A", "2": "TERM"}, sch=(129.54, 195.58, 0), pcb=(25.25, 37.2, 0))
add("JP1", JP_BRIDGED, {"1": "TERM", "2": "BUS_B"}, sch=(142.24, 208.28, 0), pcb=(26.3, 39.9, 270), nobom=True)
add("U2", P["THVD1450"], {"1": "RS485_RX", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_TX",
                          "5": "GND", "6": "BUS_A", "7": "BUS_B", "8": "+3V3"},
    sch=(190.5, 198.12, 0), pcb=(MOD_X - 4.445 + 1.905, 31.45, 270))  # logic pins under IO9..IO12
add("C12", c0603("100nF"), {"1": "+3V3", "2": "GND"}, sch=(215.9, 175.26, 0), pcb=(30.0, 34.4, 270))
add("R7", r0603("10k"), {"1": "RS485_DE", "2": "GND"}, sch=(160.02, 228.6, 0), pcb=(21.4, 31.4, 270))
add("R8", r0603("10k"), {"1": "+3V3", "2": "RS485_RX"}, sch=(160.02, 177.8, 0), pcb=(30.0, 30.4, 270))

# ---------------- LEDs and expansion --------------------------------------------------
add("R12", r0603("1k"), {"1": "+3V3", "2": "LED_PWR"}, sch=(256.54, 180.34, 0), pcb=(37.2, 42.4, 90))
add("D5", P["LED_R"], {"2": "LED_PWR", "1": "GND"}, sch=(256.54, 198.12, 90), pcb=(37.2, 46.2, 90), label="PWR")
add("R13", r0603("100"), {"1": "LED_STAT", "2": "LED_STAT_A"}, sch=(279.4, 180.34, 0), pcb=(40.6, 42.4, 90))
add("D6", P["LED_G"], {"2": "LED_STAT_A", "1": "GND"}, sch=(279.4, 198.12, 90), pcb=(40.6, 46.2, 90), label="STAT")
add("R14", r0603("100"), {"1": "LED_BUS", "2": "LED_BUS_A"}, sch=(302.26, 180.34, 0), pcb=(44.0, 42.4, 90))
add("D7", P["LED_W"], {"2": "LED_BUS_A", "1": "GND"}, sch=(302.26, 198.12, 90), pcb=(44.0, 46.2, 90), label="BUS")
add("J3", P["HDR6"], {"1": "GND", "2": "EXP_IO1", "3": "EXP_IO2",
                                                       "4": "TXD0", "5": "RXD0", "6": "+3V3"},
    sch=(365.76, 190.5, 0), pcb=(46.6, 15.6, 0), dnp=True)
for i, (x, y) in enumerate([(3.5, 10.0), (BOARD_W - 3.5, 10.0), (3.5, BOARD_H - 3.5), (BOARD_W - 3.5, BOARD_H - 3.5)], 1):
    add("H%d" % i, P["HOLE"], {}, sch=(342.9 + 12.7 * (i - 1), 231.14, 0), pcb=(x, y, 0), nobom=True)


# Nets that get wider tracks on the board
POWER_NETS = {"12V_IN": 0.6, "VIN": 0.6, "VSYS": 0.6, "VBUCK": 0.6, "VBUS": 0.5, "SW": 0.5, "+3V3": 0.5}

GPIO_MAP = [
    ("GPIO9", "RS485_TX", "UART TX to THVD1450 DI"),
    ("GPIO12", "RS485_RX", "UART RX from THVD1450 RO"),
    ("GPIO10", "RS485_DE", "Driver enable (DE and /RE), high = transmit"),
    ("GPIO38", "LED_STAT", "Green status LED, active high"),
    ("GPIO39", "LED_BUS", "White bus LED, active high"),
    ("GPIO0", "BOOT", "BOOT button, low = download mode at reset"),
    ("GPIO19/20", "USB D-/D+", "Native USB (Serial/JTAG) on USB-C"),
    ("GPIO1, GPIO2", "EXP_IO1/2", "Spare, on J3"),
    ("GPIO43/44", "TXD0/RXD0", "UART0, on J3"),
]
