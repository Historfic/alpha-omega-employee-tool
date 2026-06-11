// === PIVOT CORE START ===
const SHEET_ID = 1545975491;
const COLS = {
  Ivan:   { in: 1, out: 2, total: 7,  emergency: 10 },
  Daniel: { in: 3, out: 4, total: 8,  emergency: 11 },
};
// The pivot tab has TWO header rows (row 1 = employee names, row 2 = Date/In/Out
// labels), so the first data date 2026-06-01 sits on sheet row 3 = 0-based
// index 2. Hence the "2 +" base offset below.
const BASE_UTC = Date.UTC(2026, 5, 1);                 // 2026-06-01 = pivot row 3 (index 2)
const MS_PER_DAY = 86400000;
const MAX_INDEX = 2 + Math.round((Date.UTC(2026, 9, 20) - BASE_UTC) / MS_PER_DAY); // 2026-10-20

function rowIndexFor(dateStr) {
  const m = String(dateStr == null ? '' : dateStr).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return null;
  const utc = Date.UTC(Number(m[3]), Number(m[1]) - 1, Number(m[2]));
  const idx = 2 + Math.round((utc - BASE_UTC) / MS_PER_DAY);
  return (idx < 2 || idx > MAX_INDEX) ? null : idx;
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
