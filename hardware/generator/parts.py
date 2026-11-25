"""Part catalogue: KiCad symbol, footprint and JLCPCB/LCSC part number.

Every part number here was checked against the JLCPCB parts library on
2026-11-25 (stock and basic/extended status change over time, so check again
before you order).
"""

P = {
    # name: (symbol, footprint, value, LCSC, manufacturer part)
    "ESP32S3": ("RF_Module:ESP32-S3-WROOM-1", "RF_Module:ESP32-S3-WROOM-1",
                "ESP32-S3-WROOM-1-N8R2", "C2913204", "ESP32-S3-WROOM-1-N8R2"),
    "THVD1450": ("Interface_UART:THVD1450D", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                 "THVD1450DR", "C2671361", "THVD1450DR"),
    "SM712": ("Diode:SM712_SOT23", "Package_TO_SOT_SMD:SOT-23",
              "PSM712", "C32677", "PSM712-LF-T7"),
    "USBLC6": ("Power_Protection:USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
               "USBLC6-2SC6", "C7519", "USBLC6-2SC6"),
    "USBC": ("Connector:USB_C_Receptacle_USB2.0_16P", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
             "USB-C", "C165948", "TYPE-C-31-M-12"),
    "TERM4": ("Connector_Generic:Conn_01x04",
              "Connector_Phoenix_MC:PhoenixContact_MC_1,5_4-G-3.5_1x04_P3.50mm_Horizontal",
              "NIBE bus", "C395831", "DB2ERC-3.5-4P-GN"),
    "TPS62933": ("Regulator_Switching:TPS62933", "Package_TO_SOT_SMD:SOT-583-8",
                 "TPS62933DRLR", "C3200405", "TPS62933DRLR"),
    "L4u7": ("Device:L", "Inductor_SMD:L_Changjiang_FNR4030S", "4.7uH", "C167874", "FNR4030S4R7MT"),
    "B5819W": ("Device:D_Schottky", "Diode_SMD:D_SOD-123", "B5819W", "C8598", "B5819W SL"),
    "PTC500": ("Device:Polyfuse", "Fuse:Fuse_1206_3216Metric", "500mA/24V", "C492011", "SMD1206P050TF/24"),
    "BTN": ("Switch:SW_Push", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "TS-1187A", "C318884", "TS-1187A-B-A-B"),
    "LED_R": ("Device:LED", "LED_SMD:LED_0603_1608Metric", "red", "C2286", "KT-0603R"),
    "LED_G": ("Device:LED", "LED_SMD:LED_0805_2012Metric", "green", "C2297", "KT-0805G"),
    "LED_W": ("Device:LED", "LED_SMD:LED_0603_1608Metric", "white", "C2290", "KT-0603W"),
    "HDR6": ("Connector_Generic:Conn_01x06", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
             "EXP (not fitted)", "", ""),
    "HOLE": ("Mechanical:MountingHole", "MountingHole:MountingHole_3.2mm_M3", "M3", "", ""),
}

# 0603 resistors and capacitors (all JLCPCB basic parts)
R0603 = {
    "120": "C22787", "330": "C23138", "1k": "C21190", "5.1k": "C23186", "10k": "C25804",
    "4.7k": "C23162", "15k": "C22809", "47k": "C25819", "100k": "C25803",
}
C0603 = {"100nF": "C14663", "1uF": "C15849", "10uF": "C19702", "10nF": "C57112"}
C0805 = {"10uF/25V": "C15850", "22uF/25V": "C45783"}
