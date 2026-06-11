# Pivot Timesheet Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror every clock-in/clock-out into the pivot timesheet tab (gid 1545975491) of the *Alpha Omega Time Log* spreadsheet, in real time, by adding a parallel branch to the live `clock-in-out` n8n workflow.

**Architecture:** The pivot-write logic is a pure JS function (`tools/pivot_cells.js`) that is unit-tested locally and then inlined into a new n8n Code node. A Python script patches the live workflow JSON (fetched via the n8n public API) — patching the `Decide` node, adding the Code node and an HTTP Request node, and rewiring `Append row`/`Update row` to feed the new branch in parallel with the existing Respond nodes. Cells are addressed by sheet **gid + row/column index** (not header name) to sidestep the three duplicate "Out" headers and to control number-vs-string typing.

**Tech Stack:** n8n public API (`https://gogreen.app.n8n.cloud/api/v1`), Google Sheets REST API (`spreadsheets:batchUpdate`), Node.js (built-in `assert`, no deps), Python 3 (stdlib only), curl.

---

## Reference values (verified from the live workflow)

- n8n base URL: `https://gogreen.app.n8n.cloud`
- API key file (gitignored): `n8n_api.txt` (read at runtime; never commit/echo)
- Workflow: `clock-in-out`, id `gpThnM5QjdMrkjP1`, active
- Webhook: `GET /webhook/clock-da657ce8?employee_id=<001|002>&action=<in|out>`
- Spreadsheet id: `1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E`
- Source tab: `Sheet1` (gid `0`); Pivot tab: gid `1545975491`
- Google Sheets OAuth2 credential: id `y7Nn8fmXcH1bKw37`, name `Atutor`
- Code node typeVersion: `2`; HTTP Request typeVersion: `4.2`
- Error workflow already set: `rRTsQNBidIdyojy0`
- Employee map: `001 -> Ivan`, `002 -> Daniel`. Nae = manual (never written).
- Pivot columns (0-based index): Ivan In=1, Out=2, Total=7, Emerg=10; Daniel In=3, Out=4, Total=8, Emerg=11.
- Pivot rows: row 2 (0-based index 1) = `06/01/2026`, one contiguous row/day through `10/20/2026`.

**Windows curl note:** all curl calls to HTTPS must include `--ssl-no-revoke` (schannel revocation quirk on this machine).

---

## File Structure

- Create `tools/pivot_cells.js` — pure pivot-cell builder (single source of truth; the n8n Code node body is extracted from this file).
- Create `tools/pivot_cells.test.js` — Node `assert` unit tests for the builder.
- Create `tools/patch_workflow.py` — fetches/patches/writes the workflow PUT body (dry-run by default).
- Modify `README.md` — document the new pivot-sync branch.
- Gitignored scratch (not committed): `.wf-current.json`, `.wf-put.json`, `.wf-snapshot.json` (backup), `.probe-*.json`.

---

## Task 1: Pure pivot-cell builder + local unit tests (TDD)

**Files:**
- Create: `tools/pivot_cells.js`
- Test: `tools/pivot_cells.test.js`

- [ ] **Step 1: Write the failing tests**

Create `tools/pivot_cells.test.js`:

```js
const assert = require('assert');
const { buildPivotItems, rowIndexFor, MAX_INDEX } = require('./pivot_cells');

// Helper: wrap raw json objects as n8n items
const items = (...objs) => objs.map((json) => ({ json }));

// rowIndexFor: 06/01/2026 -> index 1 (sheet row 2); 06/11 -> 11; bounds.
assert.strictEqual(rowIndexFor('06/01/2026'), 1, 'Jun 1 -> index 1');
assert.strictEqual(rowIndexFor('06/11/2026'), 11, 'Jun 11 -> index 11');
assert.strictEqual(rowIndexFor('10/20/2026'), MAX_INDEX, 'Oct 20 -> MAX_INDEX');
assert.strictEqual(rowIndexFor('10/21/2026'), null, 'past template -> null');
assert.strictEqual(rowIndexFor('05/31/2026'), null, 'before template -> null');
assert.strictEqual(rowIndexFor('not-a-date'), null, 'garbage -> null');

// Ivan clock-in: one stringValue write to In column (index 1) on row index 11.
let out = buildPivotItems(items({
  operation: 'append', display_employee: 'Ivan', Date: '06/11/2026', Time_in: '6:02 PM',
  Time_out: '', Total_hours: '', Emergency_Log: '',
}));
assert.strictEqual(out.length, 1, 'Ivan in -> 1 output item');
let reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 1, 'Ivan in -> 1 cell');
assert.strictEqual(reqs[0].updateCells.range.sheetId, 1545975491);
assert.strictEqual(reqs[0].updateCells.range.startRowIndex, 11);
assert.strictEqual(reqs[0].updateCells.range.startColumnIndex, 1, 'Ivan In = col B (1)');
assert.strictEqual(reqs[0].updateCells.rows[0].values[0].userEnteredValue.stringValue, '6:02 PM');

// Daniel clock-out, regular: Out (string) + Total (number). Emergency empty -> skipped.
out = buildPivotItems(items({
  operation: 'update', display_employee: 'Daniel', Date: '06/11/2026',
  Time_out: '12:30 AM', Total_hours: 6, Emergency_Log: '',
}));
reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 2, 'Daniel out regular -> 2 cells');
assert.strictEqual(reqs[0].updateCells.range.startColumnIndex, 4, 'Daniel Out = col E (4)');
assert.strictEqual(reqs[0].updateCells.rows[0].values[0].userEnteredValue.stringValue, '12:30 AM');
assert.strictEqual(reqs[1].updateCells.range.startColumnIndex, 8, 'Daniel Total = col I (8)');
assert.strictEqual(reqs[1].updateCells.rows[0].values[0].userEnteredValue.numberValue, 6, 'Total is a number');

// Daniel clock-out, emergency: Total empty -> skipped; Emergency (number) written.
out = buildPivotItems(items({
  operation: 'update', display_employee: 'Daniel', Date: '06/11/2026',
  Time_out: '3:00 AM', Total_hours: '', Emergency_Log: 9,
}));
reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 2, 'emergency out -> Out + Emergency');
assert.strictEqual(reqs[1].updateCells.range.startColumnIndex, 11, 'Daniel Emerg = col L (11)');
assert.strictEqual(reqs[1].updateCells.rows[0].values[0].userEnteredValue.numberValue, 9);

// Nae -> skipped entirely (manual columns).
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Nae', Date: '06/11/2026', Time_in: '6:00 PM' })).length,
  0, 'Nae -> no writes');

// Unknown employee -> skipped.
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Unknown (999)', Date: '06/11/2026', Time_in: '6:00 PM' })).length,
  0, 'unknown -> no writes');

// Date outside template -> skipped even for a valid employee.
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Ivan', Date: '01/01/2026', Time_in: '6:00 PM' })).length,
  0, 'out-of-range date -> no writes');

console.log('ALL PIVOT TESTS PASSED');
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node tools/pivot_cells.test.js`
Expected: FAIL — `Cannot find module './pivot_cells'`.

- [ ] **Step 3: Write the implementation**

Create `tools/pivot_cells.js`. Everything between the `PIVOT CORE` markers is the exact text that will be inlined into the n8n Code node — do not reference Node globals or `require` inside that block.

```js
// === PIVOT CORE START ===
const SHEET_ID = 1545975491;
const COLS = {
  Ivan:   { in: 1, out: 2, total: 7,  emergency: 10 },
  Daniel: { in: 3, out: 4, total: 8,  emergency: 11 },
};
const BASE_UTC = Date.UTC(2026, 5, 1);                 // 2026-06-01 = pivot row 2 (index 1)
const MS_PER_DAY = 86400000;
const MAX_INDEX = 1 + Math.round((Date.UTC(2026, 9, 20) - BASE_UTC) / MS_PER_DAY); // 2026-10-20

function rowIndexFor(dateStr) {
  const m = String(dateStr == null ? '' : dateStr).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return null;
  const utc = Date.UTC(Number(m[3]), Number(m[1]) - 1, Number(m[2]));
  const idx = 1 + Math.round((utc - BASE_UTC) / MS_PER_DAY);
  return (idx < 1 || idx > MAX_INDEX) ? null : idx;
}

function cell(rowIndex, colIndex, value, kind) {
  const userEnteredValue = kind === 'number'
    ? { numberValue: Number(value) }
    : { stringValue: String(value) };
  return {
    updateCells: {
      range: {
        sheetId: SHEET_ID,
        startRowIndex: rowIndex, endRowIndex: rowIndex + 1,
        startColumnIndex: colIndex, endColumnIndex: colIndex + 1,
      },
      rows: [{ values: [{ userEnteredValue }] }],
      fields: 'userEnteredValue',
    },
  };
}

function has(v) { return v !== undefined && v !== null && v !== ''; }

function buildPivotItems(inputItems) {
  const out = [];
  for (const item of inputItems) {
    const j = item.json;
    const cols = COLS[j.display_employee || j.Employee];
    if (!cols) continue;                       // not Ivan/Daniel -> skip (e.g. Nae, Unknown)
    const rowIndex = rowIndexFor(j.Date);
    if (rowIndex === null) continue;           // date outside template -> skip
    const requests = [];
    if (j.operation === 'append') {
      if (has(j.Time_in)) requests.push(cell(rowIndex, cols.in, j.Time_in, 'string'));
    } else if (j.operation === 'update') {
      if (has(j.Time_out))      requests.push(cell(rowIndex, cols.out,       j.Time_out,      'string'));
      if (has(j.Total_hours))   requests.push(cell(rowIndex, cols.total,     j.Total_hours,   'number'));
      if (has(j.Emergency_Log)) requests.push(cell(rowIndex, cols.emergency, j.Emergency_Log, 'number'));
    }
    if (requests.length) out.push({ json: { body: { requests } } });
  }
  return out;
}
// === PIVOT CORE END ===

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { buildPivotItems, rowIndexFor, cell, COLS, SHEET_ID, MAX_INDEX };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node tools/pivot_cells.test.js`
Expected: `ALL PIVOT TESTS PASSED` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add tools/pivot_cells.js tools/pivot_cells.test.js
git commit -m "feat: pivot-cell builder for timesheet sync with unit tests"
```

---

## Task 2: Workflow patch script (dry run)

**Files:**
- Create: `tools/patch_workflow.py`

This script reads `.wf-current.json` (a fresh GET of the workflow), inlines the PIVOT CORE block from `tools/pivot_cells.js` into a new Code node, patches `Decide`, adds the HTTP node, rewires connections, and writes the PUT body to `.wf-put.json`. It does **not** call the API (that is Task 3).

- [ ] **Step 1: Write the script**

Create `tools/patch_workflow.py`:

```python
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
```

- [ ] **Step 2: Fetch a fresh copy of the live workflow**

Run:
```bash
KEY=$(tr -d '\r\n' < n8n_api.txt)
curl -s --ssl-no-revoke -H "X-N8N-API-KEY: $KEY" -H "accept: application/json" \
  "https://gogreen.app.n8n.cloud/api/v1/workflows/gpThnM5QjdMrkjP1" \
  -o .wf-current.json -w "HTTP:%{http_code}\n"
```
Expected: `HTTP:200`.

- [ ] **Step 3: Run the patch script (dry run)**

Run: `python tools/patch_workflow.py`
Expected output includes:
```
Wrote .../.wf-put.json
nodes: 15 | has Build Pivot Cells: True | has Write Pivot: True
Append row ->  ['Respond IN', 'Build Pivot Cells']
Update row ->  ['Respond OUT', 'Build Pivot Cells']
```

- [ ] **Step 4: Verify the Decide patch and the inlined node body**

Run:
```bash
python -c "import json; w=json.load(open('.wf-put.json',encoding='utf-8')); d=[n for n in w['nodes'] if n['name']=='Decide'][0]; b=[n for n in w['nodes'] if n['name']=='Build Pivot Cells'][0]; print('DECIDE has Date patch:', 'Date: row.Date' in d['parameters']['jsCode']); print('BUILD ends with return:', b['parameters']['jsCode'].strip().endswith('return buildPivotItems($input.all());')); print('BUILD has COLS:', 'Daniel' in b['parameters']['jsCode'])"
```
Expected: all three `True`.

- [ ] **Step 5: Commit**

```bash
git add tools/patch_workflow.py
git commit -m "feat: n8n workflow patch script for pivot sync (dry run)"
```

---

## Task 3: Apply the patch to the live workflow

**Files:** none created; mutates the live `clock-in-out` workflow via API.

- [ ] **Step 1: Back up the current workflow**

Run: `cp .wf-current.json .wf-snapshot.json && echo "backup saved"`
Expected: `backup saved`. (`.wf-snapshot.json` is gitignored; this is the rollback source.)

- [ ] **Step 2: PUT the patched workflow**

Run:
```bash
KEY=$(tr -d '\r\n' < n8n_api.txt)
curl -s --ssl-no-revoke -X PUT \
  -H "X-N8N-API-KEY: $KEY" -H "Content-Type: application/json" \
  --data-binary @.wf-put.json \
  "https://gogreen.app.n8n.cloud/api/v1/workflows/gpThnM5QjdMrkjP1" \
  -o .probe-put.json -w "HTTP:%{http_code}\n"
```
Expected: `HTTP:200`.
If `HTTP:400`, inspect `.probe-put.json` for `"message"`. If it names a forbidden property under `settings`, remove that key from the `safe_settings` allowlist in `patch_workflow.py`, re-run Task 2 Step 3, and retry this step.

- [ ] **Step 3: Verify the live graph now has the new nodes and wiring**

Run:
```bash
KEY=$(tr -d '\r\n' < n8n_api.txt)
curl -s --ssl-no-revoke -H "X-N8N-API-KEY: $KEY" \
  "https://gogreen.app.n8n.cloud/api/v1/workflows/gpThnM5QjdMrkjP1" -o .wf-current.json
python -c "import json; w=json.load(open('.wf-current.json',encoding='utf-8')); names=[n['name'] for n in w['nodes']]; c=w['connections']; print('active:', w.get('active')); print('has nodes:', 'Build Pivot Cells' in names, 'Write Pivot' in names); print('Append row ->', [x['node'] for x in c['Append row']['main'][0]]); print('Build Pivot Cells ->', [x['node'] for x in c['Build Pivot Cells']['main'][0]])"
```
Expected:
```
active: True
has nodes: True True
Append row -> ['Respond IN', 'Build Pivot Cells']
Build Pivot Cells -> ['Write Pivot']
```

- [ ] **Step 4: Force a redeploy (deactivate + reactivate)**

Ensures the running instance picks up the new graph and the webhook is re-registered.
```bash
KEY=$(tr -d '\r\n' < n8n_api.txt)
curl -s --ssl-no-revoke -X POST -H "X-N8N-API-KEY: $KEY" \
  "https://gogreen.app.n8n.cloud/api/v1/workflows/gpThnM5QjdMrkjP1/deactivate" -w "deact:%{http_code}\n" -o /dev/null
curl -s --ssl-no-revoke -X POST -H "X-N8N-API-KEY: $KEY" \
  "https://gogreen.app.n8n.cloud/api/v1/workflows/gpThnM5QjdMrkjP1/activate" -w "act:%{http_code}\n" -o /dev/null
```
Expected: `deact:200` then `act:200`.

(No commit — this task only changes server state.)

---

## Task 4: Live end-to-end verification

**Files:** none. Exercises the production webhook once for Ivan, then verifies the pivot via the public CSV export. Today's date is `06/11/2026` -> pivot **row 12** (index 11), Ivan columns **B** (In), **C** (Out), **H** (Total).

> **Heads-up (no programmatic cleanup):** this machine can only *read* the sheet (public CSV export); it cannot write to it. The test below creates a real Sheet1 row + pivot cells for Ivan today. After verifying, the sheet owner must either delete that Sheet1 row and clear B12/C12/H12 by hand, or accept it as a genuine clock entry. Skip this task and test with a real scan instead if that is preferable.

- [ ] **Step 1: Trigger a clock-IN for Ivan (001)**

Run:
```bash
curl -s --ssl-no-revoke "https://gogreen.app.n8n.cloud/webhook/clock-da657ce8?employee_id=001&action=in" -o .probe-in.html -w "HTTP:%{http_code}\n"
grep -o 'Clock In\|Already Clocked In\|EMERGENCY\|ON TIME\|LATE\|EARLY' .probe-in.html | head -3
```
Expected: `HTTP:200` and a clock-in page (e.g. `Clock In`). If it shows `Already Clocked In`, Ivan already has an open shift today — go straight to Step 3 (clock OUT) to close and test the update path, then re-run from Step 1 if needed.

- [ ] **Step 2: Verify the pivot In cell filled (column B, row 12)**

Run (wait ~10s first for Sheets to settle):
```bash
sleep 10
curl -s --ssl-no-revoke -L "https://docs.google.com/spreadsheets/d/1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E/export?format=csv&gid=1545975491&range=A12:H12" -o .probe-pivot.csv
cat .probe-pivot.csv
```
Expected: one CSV line; first field is `06/01/2026`+10 days = `06/11/2026`'s row, and the 2nd field (column **B**, Ivan In) holds the clock-in time (e.g. `6:02 PM`). Fields 4-7 (Daniel/Nae) remain empty.

- [ ] **Step 3: Trigger a clock-OUT for Ivan (001)**

Run:
```bash
curl -s --ssl-no-revoke "https://gogreen.app.n8n.cloud/webhook/clock-da657ce8?employee_id=001&action=out" -o .probe-out.html -w "HTTP:%{http_code}\n"
grep -o 'Clock Out\|OVERTIME\|ON TIME\|EARLY OUT\|Emergency' .probe-out.html | head -3
```
Expected: `HTTP:200` and a clock-out page.

- [ ] **Step 4: Verify Out + Total filled (columns C and H, row 12)**

Run:
```bash
sleep 10
curl -s --ssl-no-revoke -L "https://docs.google.com/spreadsheets/d/1yms8rFDnPo-QRENrdSY6PJ2i11Shdd7RAc14jktCj9E/export?format=csv&gid=1545975491&range=A12:H12" -o .probe-pivot2.csv
cat .probe-pivot2.csv
```
Expected: the 3rd field (column **C**, Ivan Out) now holds the clock-out time and the 8th field (column **H**, Total Ivan) holds the total hours as a bare number (e.g. `0`, not `"0"`). Daniel/Nae columns still empty.

- [ ] **Step 5: Confirm the n8n execution succeeded**

Run:
```bash
KEY=$(tr -d '\r\n' < n8n_api.txt)
curl -s --ssl-no-revoke -H "X-N8N-API-KEY: $KEY" \
  "https://gogreen.app.n8n.cloud/api/v1/executions?workflowId=gpThnM5QjdMrkjP1&limit=3" \
  | python -c "import sys,json; d=json.load(sys.stdin); [print(e['id'], e.get('status'), e.get('startedAt')) for e in d.get('data',[])]"
```
Expected: the two most recent executions show `status: success` (a `Write Pivot` error would show `error` here even though the clock response still returned, because of continue-on-error — investigate `.probe-*.html` and the execution if so).

(No commit — verification only. Inform the owner about manual cleanup of the test cells.)

---

## Task 5: Document and commit

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a section to README.md**

Insert after the `## Sheet columns` section:

```markdown
## Pivot timesheet sync

A second tab in the same spreadsheet (gid `1545975491`) is a human-readable
monthly timesheet: one row per date, with Ivan and Daniel side-by-side in
columns. The `clock-in-out` workflow mirrors each scan into it in real time:

- A `Build Pivot Cells` Code node (logic mirrored in `tools/pivot_cells.js`)
  turns each clock event into Google Sheets `updateCells` requests, addressing
  cells by sheet gid + row/column index.
- A `Write Pivot` HTTP node POSTs them to `spreadsheets:batchUpdate` using the
  existing `Atutor` Google Sheets credential. It runs in parallel with the
  Respond nodes and is set to continue-on-error, so it never blocks or breaks an
  employee's clock-in/out.

Mapping: `kaz`/`001` -> Ivan (cols B/C/H/K), `david`/`002` -> Daniel
(cols D/E/I/L). **Nae's columns (F/G/J/M) are manual and never written.**
Rows are resolved deterministically (row 2 = 06/01/2026, one row/day). When the
timesheet is extended past 10/20/2026, widen the date window in
`tools/pivot_cells.js` (`MAX_INDEX`).

Edit the workflow with `tools/patch_workflow.py` (requires `n8n_api.txt`).
Unit-test the cell builder with `node tools/pivot_cells.test.js`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md docs/superpowers/plans/2026-06-11-pivot-timesheet-sync.md
git commit -m "docs: document pivot timesheet sync"
```

---

## Self-Review

**Spec coverage:** Decide patch (Task 2 Step 1 `patch_decide`), Build Pivot Cells node (Tasks 1 + 2), Write Pivot HTTP node with Atutor cred + continue-on-error (Task 2), gid+index addressing & number/string typing (Task 1), deterministic row + out-of-range guard (Task 1 `rowIndexFor`), parallel non-blocking wiring (Task 2 `add_conn`), Nae-safe / Ivan+Daniel-only (Task 1 `COLS`), cross-midnight IN-date (Decide emits `row.Date`, consumed in Task 1), apply + verify (Task 3), e2e (Task 4), docs (Task 5). All spec sections covered.

**Out of scope (per spec):** no backfill, no QR/page/bucket/hours changes, no Nae automation — none added.

**Type consistency:** `buildPivotItems`, `rowIndexFor`, `cell`, `has`, `COLS`, `MAX_INDEX` used identically across the implementation and tests; n8n node body calls `buildPivotItems($input.all())`; Decide emits `Date`/`Employee` consumed as `j.Date`/`j.display_employee||j.Employee`.
