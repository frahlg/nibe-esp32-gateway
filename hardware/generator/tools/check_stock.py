"""Check every LCSC part in the JLCPCB BOM against the JLCPCB parts library.

Usage:  python3 hardware/generator/tools/check_stock.py [path/to/bom.csv]
Prints stock, price and basic/extended status, and exits non-zero if a part
is out of stock or has fewer than 100 in stock.
"""
import csv
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BOM = os.path.join(HERE, "..", "..", "production", "nibe-esp32-gateway-bom-jlcpcb.csv")
API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def lookup(code):
    req = urllib.request.Request(API, data=json.dumps({"keyword": code, "currentPage": 1, "pageSize": 5}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    rows = json.load(urllib.request.urlopen(req, timeout=30))["data"]["componentPageInfo"]["list"] or []
    return next((r for r in rows if r.get("componentCode") == code), None)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else BOM
    bad = 0
    total = 0.0
    print("%-10s %-9s %8s %8s  %s" % ("LCSC", "library", "stock", "price", "part"))
    for row in csv.DictReader(open(path)):
        code = row["LCSC Part #"]
        qty = len(row["Designator"].split(","))
        r = lookup(code)
        if r is None:
            print("%-10s NOT FOUND (%s)" % (code, row["Comment"]))
            bad += 1
            continue
        price = (r.get("componentPrices") or [{}])[0].get("productPrice") or 0
        total += price * qty
        lib = {"base": "basic", "expand": "extended"}.get(r.get("componentLibraryType"), r.get("componentLibraryType"))
        flag = "" if r["stockCount"] >= 100 else "   <-- LOW STOCK"
        bad += 1 if flag else 0
        print("%-10s %-9s %8d %8.3f  %s x%d%s" % (code, lib, r["stockCount"], price, r.get("componentModelEn"), qty, flag))
    print("parts cost per board at 1-piece prices: $%.2f" % total)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
