#!/usr/bin/env python3
"""Patch the clock-in-out workflow to mirror clock events into the pivot tab.
Reads .wf-current.json, writes .wf-put.json (the PUT body). No network calls."""
import json, re, sys, uuid, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CUR = ROOT / ".wf-current.json"
OUT = ROOT / ".wf-put.json"
CORE = ROOT / "tools" / "pivot_cells.js"

CRED = {"googleSheetsOAuth2Api": {"id": "y7Nn8fmXcH1bKw37", "name": "Atutor"}}
SPREADSHEET = "1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E"


def extract_core():
    text = CORE.read_text(encoding="utf-8")
    m = re.search(r"// === PIVOT CORE START ===\n(.*)// === PIVOT CORE END ===",
                  text, re.S)
    if not m:
        sys.exit("ERROR: PIVOT CORE markers not found in pivot_cells.js")
    return m.group(1).rstrip() + "\n\nreturn buildPivotItems($input.all());\n"


def patch_decide(node):
    code = node["parameters"]["jsCode"]
    needle = "    operation: 'update',\n    row_number: row.row_number,\n"
    add = ("    operation: 'update',\n    row_number: row.row_number,\n"
           "    Date: row.Date,\n    Employee: employeeName,\n")
    if needle not in code:
        sys.exit("ERROR: could not find the Decide update-return block to patch")
    if code.count(needle) != 1:
        sys.exit("ERROR: Decide update block matched %d times (expected 1)"
                 % code.count(needle))
    node["parameters"]["jsCode"] = code.replace(needle, add)


def main():
    wf = json.loads(CUR.read_text(encoding="utf-8"))
    nodes = wf["nodes"]
    conns = wf["connections"]
    by_name = {n["name"]: n for n in nodes}
    for required in ("Decide", "Append row", "Update row"):
        if required not in by_name:
            sys.exit("ERROR: node '%s' missing" % required)

    # 1) Patch Decide (idempotency guard: skip if already patched).
    if "Date: row.Date" not in by_name["Decide"]["parameters"]["jsCode"]:
        patch_decide(by_name["Decide"])

    # 2) Add Build Pivot Cells (Code) node.
    build = {
        "parameters": {"jsCode": extract_core()},
        "id": str(uuid.uuid4()),
        "name": "Build Pivot Cells",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1680, 200],
    }

    # 3) Add Write Pivot (HTTP Request) node.
    write = {
        "parameters": {
            "method": "POST",
            "url": ("https://sheets.googleapis.com/v4/spreadsheets/"
                    + SPREADSHEET + ":batchUpdate"),
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleSheetsOAuth2Api",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {},
        },
        "id": str(uuid.uuid4()),
        "name": "Write Pivot",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1900, 200],
        "credentials": CRED,
        "onError": "continueRegularOutput",
    }

    # Replace existing copies if re-running, else append.
    nodes = [n for n in nodes if n["name"] not in ("Build Pivot Cells", "Write Pivot")]
    nodes.extend([build, write])

    # 4) Wire connections (parallel to the Respond nodes).
    def add_conn(src, dst):
        conns.setdefault(src, {}).setdefault("main", [[]])
        if not conns[src]["main"]:
            conns[src]["main"] = [[]]
        targets = conns[src]["main"][0]
        if not any(c["node"] == dst for c in targets):
            targets.append({"node": dst, "type": "main", "index": 0})

    add_conn("Append row", "Build Pivot Cells")
    add_conn("Update row", "Build Pivot Cells")
    conns["Build Pivot Cells"] = {"main": [[{"node": "Write Pivot", "type": "main", "index": 0}]]}

    # 5) Build the PUT body (only fields the public API accepts).
    settings = wf.get("settings", {})
    safe_settings = {k: settings[k] for k in
                     ("executionOrder", "callerPolicy", "errorWorkflow",
                      "saveDataErrorExecution", "saveDataSuccessExecution",
                      "saveManualExecutions", "timezone")
                     if k in settings}
    put = {"name": wf["name"], "nodes": nodes,
           "connections": conns, "settings": safe_settings}
    OUT.write_text(json.dumps(put, indent=2), encoding="utf-8")
    print("Wrote", OUT)
    print("nodes:", len(nodes),
          "| has Build Pivot Cells:", any(n["name"] == "Build Pivot Cells" for n in nodes),
          "| has Write Pivot:", any(n["name"] == "Write Pivot" for n in nodes))
    print("Append row -> ", [c["node"] for c in conns["Append row"]["main"][0]])
    print("Update row -> ", [c["node"] for c in conns["Update row"]["main"][0]])


if __name__ == "__main__":
    main()
