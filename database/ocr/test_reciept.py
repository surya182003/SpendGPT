from receipt_parser import parse_receipt_text, validate_receipt

LIDL = """
L
DI
W1lton - IE95136747
EUR
Red Onions
0.99 A
Lidi Plus Offerg
-0.30
Heavy Duty Bag 38L
0.99 C
Fusilli
1.35 A
Oaties
0.59 B
Chocolate Digestives
0.79 C
Chickpeas In Water
0.43 A
Savings
-0.04
Dry Roasted Peanuts
2.09 C
Savings
-0.10
Mixed Vegetables
0.99 A
Redten Chicken Dippers 450g
1.69 A
Whole Milk 3.5%
1.15 A
Natural Yogurt 1.52
0.65 A
Oregano
0.59 A
Garlic Net 200g per p_
0.99 A
Chicken Minl Fille
3.49 A
Gyoza with vegetables
2.49 A
TOTAL
18.83
Credit Card
18.83
TOTAL SAVINGS
0.44
A
0.0% VAT
14.47
0.00
0.59
B
13.5% VAT
0.07
c
23.0% VAT
3.77
0.70
TRN-ID:IE019781147388276261
***CUSTOMER COPY***
Date: 03/10/26
Time: 21:31:18
TID: xxxx8601
MID: xxx98565
***********8107
DEBIT MASTERCARD
Contactless
SALE
€18.83
APPRCVED
AUTH CODE 243426
Total Savings with Lidl Plus
0.30 EUR
"""

CODES = """
Tesco Wilton
Description Price
5012345678900 Brown Bread 1.89
4001234567890
Cheese Slices
2.50
Apples
3 x 0.80
2.40
Goods: 6.79
Total: EUR6.79
Card Sales EUR 6.79
************1234
AUTH CODE 123456
Please retain receipt
Date: 12/10/26
"""

# Real Aldi OCR output: split "T o t a 1" label, split "3 X 0.79" quantity
# line that comes BEFORE its product, Cyrillic look-alike letters,
# "0.79 0" (tax code E misread as 0), and a code followed by "6PK".
ALDI = (
    "Aldi Stores (Ireland) Ltd\nElysian\nCork\nEUR\n"
    "381837 BREAO WHOLEMEAL\n0.99 E\n3\nX\n0.79\n"
    "227567 TUNA SWATER 1456\n2.37 E\n"
    "646397 ТОМАТО KETCHUP\n1.39 E\n"
    "336032 SAUCE PASTA 500G\n0,96 E\n"
    "381903 DIGESTIVES MILK\n0.79 0\n"
    "683580 PROTEIN WRAP\n1,35 E\n"
    "275578 6PK TOMATOES\n1.29 E\n"
    "719381 CAULDRON TOFU\n1.99 E\n"
    "678506 SRIRACHA\n1.99 E\n"
    "286085 BEANS MIXED 400G\n0.49 E\n"
    "T\no\nt\na 1\n13.61\n12 Items\nCard Sales\nEUR\n13.61\n"
    "D 23.0% Net\n0.64 Vat\n0.15\n0.00\nE 00.0¾ Net\n12.82 Vat\n"
    "x9572 D093/008/802 07.10.26 18:43\n"
    "Merchant 10: xxx 01524\nTerminal ID: xxx 6001\nEFT No: 7657\n"
    "07/10/26\nSALE\nGoods: 13.61\nTotal: EUR13.61\nAPPROVED\n"
    "Authorisation Code: 416630\nCUSTOMER COPY\n"
)


def show(name, text):
    r = validate_receipt(parse_receipt_text(text))
    print(f"== {name}: total={r['total_amount']} via {r['total_source']}, "
          f"items={len(r['items'])}, issues={r['validation_issues']}")
    for it in r["items"]:
        print("  ", it["product_code"], it["item_name"], it["quantity"],
              it["unit_price"], "-", it["discount"], "=", it["line_total"])
    return r


lidl = show("lidl", LIDL)
assert lidl["total_amount"] == 18.83 and len(lidl["items"]) == 15
assert not lidl["requires_review"]

codes = show("codes", CODES)
assert codes["total_amount"] == 6.79 and len(codes["items"]) == 3
assert not codes["requires_review"]

aldi = show("aldi", ALDI)
assert aldi["total_amount"] == 13.61 and len(aldi["items"]) == 10
assert aldi["item_count"] == 12
assert not aldi["requires_review"], aldi["validation_issues"]
tuna = next(i for i in aldi["items"] if "TUNA" in i["item_name"])
assert tuna["quantity"] == 3 and tuna["unit_price"] == 0.79
assert any(i["item_name"] == "TOMATO KETCHUP" for i in aldi["items"])
assert any(i["product_code"] == "275578" for i in aldi["items"])

# A lone price must never become the total.
no_total = validate_receipt(parse_receipt_text("Milk\n1.15 A\nBread\n1.89 A\n"))
assert no_total["total_amount"] is None and no_total["requires_review"]

print("all good")