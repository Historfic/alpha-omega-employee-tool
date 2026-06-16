// === PIVOT CORE START ===
const SHEET_ID = 1545975491;                 // pivot tab "Sheet2"
const COLS = {
  Ivan:   { in: 1, out: 2, total: 7,  emergency: 10 },
  Daniel: { in: 3, out: 4, total: 8,  emergency: 11 },
};
const DATE_COL = 0;

// Normalize any supported date string to zero-padded MM/DD/YYYY, else null.
function normDate(s) {
  const t = String(s == null ? '' : s).trim();
  let m = t.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) return m[1].padStart(2, '0') + '/' + m[2].padStart(2, '0') + '/' + m[3];
  m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return m[2].padStart(2, '0') + '/' + m[3].padStart(2, '0') + '/' + m[1];
  return null;
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

// decideItems: the canonical clock event(s) from the Decide node.
// colA: pivot column A values (index 0 = sheet row 1), used to find the row.
function buildPivotItems(decideItems, colA) {
  // Map normalized date -> 0-based row index; track the last dated row.
  const dateToRow = new Map();
  let lastDatedRow = -1;
  for (let i = 0; i < colA.length; i++) {
    const nd = normDate(colA[i]);
    if (nd) {
      if (!dateToRow.has(nd)) dateToRow.set(nd, i);
      lastDatedRow = i;
    }
  }
  // No dates found at all => treat as a failed/empty read and skip, so we never
  // append duplicate rows when the pivot lookup is unavailable.
  if (dateToRow.size === 0) return [];

  const out = [];
  for (const item of decideItems) {
    const j = item.json;
    const cols = COLS[j.display_employee || j.Employee];
    if (!cols) continue;                       // not Ivan/Daniel -> skip (e.g. Nae)
    const nd = normDate(j.Date);
    if (!nd) continue;

    let rowIndex;
    let isNewRow = false;
    if (dateToRow.has(nd)) {
      rowIndex = dateToRow.get(nd);
    } else {
      rowIndex = lastDatedRow + 1;             // append just after the last date
      isNewRow = true;
    }

    const requests = [];
    if (isNewRow) requests.push(cell(rowIndex, DATE_COL, nd, 'string'));
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
  module.exports = { buildPivotItems, normDate, cell, COLS, SHEET_ID };
}
