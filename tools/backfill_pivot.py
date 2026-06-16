#!/usr/bin/env python3
"""Rebuild the pivot timesheet from the full Sheet1 log.

Reads .probe-src.csv (a CSV export of Sheet1), pivots every row into a
contiguous one-row-per-day layout (Ivan + Daniel columns; Nae left blank),
and emits .backfill-wf.json: a temporary n8n workflow (webhook -> HTTP) that
writes the whole block to the pivot tab via the Atutor Google credential.

Run, then create/activate/trigger/delete the temp workflow (see chat steps)."""
import csv, json, datetime, pathlib, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / ".probe-src.csv"
OUT_WF = ROOT / ".backfill-wf.json"

PIVOT_GID = 1545975491
SPREADSHEET = "1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E"
CRED = {"googleSheetsOAuth2Api": {"id": "y7Nn8fmXcH1bKw37", "name": "Atutor"}}

# 0-based column index in the pivot row for each (employee, field).
LAYOUT = {
    "Ivan":   {"in": 1, "out": 2, "total": 7,  "emergency": 10},
    "Daniel": {"in": 3, "out": 4, "total": 8,  "emergency": 11},
}
DATE_COL = 0
ROW_WIDTH = 13  # A..M


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.date(*datetime.datetime.strptime(s, fmt).timetuple()[:3])
        except ValueError:
            continue
    return None


def num_or_str(s):
    """Return ('number', float) for numeric strings, else ('string', s)."""
    s = (s or "").strip()
    if s == "":
        return None
    try:
        n = float(s)
        return ("number", int(n) if n == int(n) else n)
    except ValueError:
        return ("string", s)


def cell(value):
    """Build a CellData. None -> empty cell (clears any stray content)."""
    if value is None:
        return {}
    kind, v = value
    return {"userEnteredValue": ({"numberValue": v} if kind == "number"
                                 else {"stringValue": v})}


def main():
    # date -> {employee -> {in/out/total/emergency: typed-or-None}}
    by_date = {}
    skipped = []
    with open(SRC, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            row = (row + [""] * 6)[:6]
            date, emp, tin, tout, total, emerg = row
            d = parse_date(date)
            if d is None or emp.strip() not in LAYOUT:
                skipped.append(row)
                continue
            rec = by_date.setdefault(d, {})
            rec[emp.strip()] = {
                "in": num_or_str(tin),
                "out": num_or_str(tout),
                "total": num_or_str(total),
                "emergency": num_or_str(emerg),
            }

    if not by_date:
        raise SystemExit("ERROR: no usable rows parsed from %s" % SRC)

    start, end = min(by_date), max(by_date)
    # Contiguous daily rows from earliest to latest date present.
    dates = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]

    # Build ONE updateCells request PER non-empty cell. Never writes empty
    # cells (no blanking) and never touches Nae's columns (F/G/J/M) -- only the
    # Date column plus Ivan/Daniel values that actually exist.
    requests = []

    def add_cell(row_index, col_index, typed):
        if typed is None:
            return
        kind, v = typed
        uev = {"numberValue": v} if kind == "number" else {"stringValue": v}
        requests.append({"updateCells": {
            "range": {"sheetId": PIVOT_GID,
                      "startRowIndex": row_index, "endRowIndex": row_index + 1,
                      "startColumnIndex": col_index, "endColumnIndex": col_index + 1},
            "rows": [{"values": [{"userEnteredValue": uev}]}],
            "fields": "userEnteredValue"}})

    preview_rows = []
    filled_dates = 0
    for i, d in enumerate(dates):
        row_index = 2 + i                       # sheet row 3 = index 2
        add_cell(row_index, DATE_COL, ("string", d.strftime("%m/%d/%Y")))
        rec = by_date.get(d)
        pv = {"row": row_index + 1, "date": d.strftime("%m/%d/%Y")}
        if rec:
            filled_dates += 1
            for emp, fields in rec.items():
                cols = LAYOUT[emp]
                add_cell(row_index, cols["in"], fields["in"])
                add_cell(row_index, cols["out"], fields["out"])
                add_cell(row_index, cols["total"], fields["total"])
                add_cell(row_index, cols["emergency"], fields["emergency"])
                for fld in ("in", "out", "total", "emergency"):
                    val = fields[fld]
                    pv["%s_%s" % (emp, fld)] = "" if val is None else val[1]
        preview_rows.append(pv)

    body = {"requests": requests}

    # Human-readable preview of exactly what will be written.
    PREVIEW = ROOT / ".backfill-preview.csv"
    cols = ["row", "date",
            "Ivan_in", "Ivan_out", "Ivan_total", "Ivan_emergency",
            "Daniel_in", "Daniel_out", "Daniel_total", "Daniel_emergency"]
    with open(PREVIEW, "w", newline="", encoding="utf-8") as pf:
        w = csv.DictWriter(pf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(preview_rows)

    # Temp workflow: webhook -> HTTP batchUpdate (embeds the body literally).
    path = "backfill-" + uuid.uuid4().hex[:8]
    wf = {
        "name": "pivot-backfill-temp",
        "nodes": [
            {
                "parameters": {"httpMethod": "GET", "path": path,
                               "responseMode": "lastNode", "options": {}},
                "id": str(uuid.uuid4()), "name": "Webhook",
                "type": "n8n-nodes-base.webhook", "typeVersion": 2.1,
                "position": [0, 0], "webhookId": str(uuid.uuid4()),
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": ("https://sheets.googleapis.com/v4/spreadsheets/"
                            + SPREADSHEET + ":batchUpdate"),
                    "authentication": "predefinedCredentialType",
                    "nodeCredentialType": "googleSheetsOAuth2Api",
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": json.dumps(body),
                    "options": {},
                },
                "id": str(uuid.uuid4()), "name": "Write",
                "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
                "position": [240, 0], "credentials": CRED,
            },
        ],
        "connections": {"Webhook": {"main": [[{"node": "Write", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
    }
    OUT_WF.write_text(json.dumps(wf), encoding="utf-8")

    print("date range:", start, "->", end, "| date rows:", len(dates),
          "| dates with data:", filled_dates)
    print("cells to write (non-empty only):", len(requests),
          "| Nae columns touched: NONE")
    print("skipped source rows:", len(skipped))
    for r in skipped:
        print("  SKIP:", r)
    print("preview written to .backfill-preview.csv")
    print("webhook path:", path)
    print("wrote", OUT_WF)


if __name__ == "__main__":
    main()
