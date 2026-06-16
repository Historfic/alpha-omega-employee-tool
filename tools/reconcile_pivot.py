#!/usr/bin/env python3
"""Reconcile the pivot tab to EXACTLY match the current Sheet1 log.

Reads .src.csv (Sheet1) and .piv.csv (current pivot), computes a per-cell DIFF
over the Ivan/Daniel/Date columns only (never Nae's F/G/J/M), and emits a
temp n8n workflow (.reconcile-wf.json) that sets/clears just the wrong cells.

Duplicate (date, employee) rows in Sheet1: last row wins.
"""
import csv, json, datetime, pathlib, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / ".src.csv"
PIV = ROOT / ".piv.csv"
OUT_WF = ROOT / ".reconcile-wf.json"
PREVIEW = ROOT / ".reconcile-preview.txt"

PIVOT_GID = 1545975491
SPREADSHEET = "1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E"
CRED = {"googleSheetsOAuth2Api": {"id": "y7Nn8fmXcH1bKw37", "name": "Atutor"}}

# Rows 1..37 are already recorded and must NOT be touched; only manage 38+.
MIN_ROW = 38

# employee -> {field: 0-based column}.  Date is column 0.
LAYOUT = {
    "Ivan":   {"in": 1, "out": 2, "total": 7,  "emergency": 10},
    "Daniel": {"in": 3, "out": 4, "total": 8,  "emergency": 11},
}
DATE_COL = 0
NUMERIC_COLS = {7, 8, 10, 11}                 # totals + emergency
MANAGED_COLS = [0, 1, 2, 3, 4, 7, 8, 10, 11]  # excludes Nae (5,6,9,12)
COL_LETTER = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E",
              7: "H", 8: "I", 10: "K", 11: "L"}


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            t = datetime.datetime.strptime(s, fmt)
            return datetime.date(t.year, t.month, t.day)
        except ValueError:
            continue
    return None


def main():
    # ---- expected values from Sheet1 (last row wins per date+employee) ----
    expected = {}     # date -> {emp -> {field: raw string}}
    with open(SRC, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if not row or not any(c.strip() for c in row):
                continue
            row = (row + [""] * 6)[:6]
            date, emp, tin, tout, total, emerg = (c.strip() for c in row)
            d = parse_date(date)
            if d is None or emp not in LAYOUT:
                continue
            expected.setdefault(d, {})[emp] = {
                "in": tin, "out": tout, "total": total, "emergency": emerg}

    if not expected:
        raise SystemExit("ERROR: no usable Sheet1 rows")
    start, end = min(expected), max(expected)
    dates = [start + datetime.timedelta(days=i)
             for i in range((end - start).days + 1)]
    date_to_row = {d: 3 + i for i, d in enumerate(dates)}   # 1-based sheet row

    # Build expected[sheet_row][col] = string ("" means empty/clear).
    exp_cell = {}
    for d in dates:
        sr = date_to_row[d]
        exp_cell[(sr, DATE_COL)] = d.strftime("%m/%d/%Y")
        for emp, fields in expected.get(d, {}).items():
            cols = LAYOUT[emp]
            for fld, col in cols.items():
                exp_cell[(sr, col)] = fields[fld]

    # ---- current pivot cells ----
    with open(PIV, newline="", encoding="utf-8") as f:
        pij = list(csv.reader(f))
    pivot_last_row = len(pij)                  # 1-based count of lines

    def cur(sr, col):
        if sr - 1 < len(pij):
            rowv = pij[sr - 1]
            if col < len(rowv):
                return rowv[col].strip()
        return ""

    # Manage every row from 3 down to whichever extends further: the date range
    # or the current pivot extent (to clear stray rows like 2027-2029).
    last_managed_row = max(date_to_row[end], pivot_last_row)

    def norm(s):
        return str(s).strip()

    requests = []
    changes = []   # (cellref, old, new)
    for sr in range(max(3, MIN_ROW), last_managed_row + 1):
        for col in MANAGED_COLS:
            want = exp_cell.get((sr, col), "")     # "" => should be empty
            have = cur(sr, col)
            if norm(have) == norm(want):
                continue
            ref = "%s%d" % (COL_LETTER[col], sr)
            changes.append((ref, have, want))
            rng = {"sheetId": PIVOT_GID,
                   "startRowIndex": sr - 1, "endRowIndex": sr,
                   "startColumnIndex": col, "endColumnIndex": col + 1}
            if want == "":
                values = [{"values": [{}]}]        # clear the cell
            else:
                if col in NUMERIC_COLS:
                    try:
                        n = float(want)
                        uev = {"numberValue": int(n) if n == int(n) else n}
                    except ValueError:
                        uev = {"stringValue": want}
                else:
                    uev = {"stringValue": want}
                values = [{"values": [{"userEnteredValue": uev}]}]
            requests.append({"updateCells": {"range": rng, "rows": values,
                                             "fields": "userEnteredValue"}})

    body = {"requests": requests}

    # ---- preview ----
    sets = [c for c in changes if c[2] != ""]
    clears = [c for c in changes if c[2] == ""]
    lines = ["RECONCILE PREVIEW  (Sheet1 date range %s .. %s)" % (start, end),
             "cells to change: %d  (set %d, clear %d) | Nae cols never touched"
             % (len(changes), len(sets), len(clears)), ""]
    lines.append("--- SET (fix to Sheet1 value) ---")
    for ref, old, new in sets:
        lines.append("  %-5s  '%s'  ->  '%s'" % (ref, old, new))
    lines.append("--- CLEAR (remove foreign / stray) ---")
    for ref, old, new in clears:
        lines.append("  %-5s  '%s'  ->  (empty)" % (ref, old))
    PREVIEW.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    # ---- temp workflow ----
    path = "reconcile-" + uuid.uuid4().hex[:8]
    wf = {
        "name": "pivot-reconcile-temp",
        "nodes": [
            {"parameters": {"httpMethod": "GET", "path": path,
                            "responseMode": "lastNode", "options": {}},
             "id": str(uuid.uuid4()), "name": "Webhook",
             "type": "n8n-nodes-base.webhook", "typeVersion": 2.1,
             "position": [0, 0], "webhookId": str(uuid.uuid4())},
            {"parameters": {
                "method": "POST",
                "url": ("https://sheets.googleapis.com/v4/spreadsheets/"
                        + SPREADSHEET + ":batchUpdate"),
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "googleSheetsOAuth2Api",
                "sendBody": True, "specifyBody": "json",
                "jsonBody": json.dumps(body), "options": {}},
             "id": str(uuid.uuid4()), "name": "Write",
             "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
             "position": [240, 0], "credentials": CRED},
        ],
        "connections": {"Webhook": {"main": [[{"node": "Write", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
    }
    OUT_WF.write_text(json.dumps(wf), encoding="utf-8")
    print("\nwebhook path:", path, "| wrote", OUT_WF.name)


if __name__ == "__main__":
    main()
