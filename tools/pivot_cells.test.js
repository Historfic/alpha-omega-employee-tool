const assert = require('assert');
const { buildPivotItems, normDate } = require('./pivot_cells');

// Helper: wrap raw json objects as n8n items
const items = (...objs) => objs.map((json) => ({ json }));

// Pivot column A as returned by values.get (index 0 = sheet row 1).
// Two header rows, then dates from row 3 (index 2).
const colA = ['', 'Date', '05/04/2026', '05/05/2026', '06/11/2026'];

// normDate: accepts MM/DD/YYYY and YYYY-MM-DD, zero-pads, else null.
assert.strictEqual(normDate('06/11/2026'), '06/11/2026');
assert.strictEqual(normDate('2026-05-13'), '05/13/2026');
assert.strictEqual(normDate('6/1/2026'), '06/01/2026');
assert.strictEqual(normDate('garbage'), null);

// Empty/failed pivot read -> skip everything (never append duplicates).
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Ivan', Date: '06/11/2026', Time_in: '6:02 PM' }), []).length,
  0, 'empty colA -> no writes');

// Ivan clock-in, existing date 06/11 (index 4): 1 cell to In col (1), no date write.
let out = buildPivotItems(items({
  operation: 'append', display_employee: 'Ivan', Date: '06/11/2026', Time_in: '6:02 PM',
  Time_out: '', Total_hours: '', Emergency_Log: '',
}), colA);
let reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 1, 'existing date in -> 1 cell');
assert.strictEqual(reqs[0].updateCells.range.startRowIndex, 4, 'row index 4');
assert.strictEqual(reqs[0].updateCells.range.startColumnIndex, 1, 'Ivan In = col B (1)');
assert.strictEqual(reqs[0].updateCells.rows[0].values[0].userEnteredValue.stringValue, '6:02 PM');

// Daniel clock-out, existing date 05/04 (index 2): Out (string) + Total (number).
out = buildPivotItems(items({
  operation: 'update', display_employee: 'Daniel', Date: '05/04/2026',
  Time_out: '10:13:00 AM', Total_hours: 3, Emergency_Log: '',
}), colA);
reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 2, 'out regular -> 2 cells');
assert.strictEqual(reqs[0].updateCells.range.startColumnIndex, 4, 'Daniel Out = col E (4)');
assert.strictEqual(reqs[1].updateCells.range.startColumnIndex, 8, 'Daniel Total = col I (8)');
assert.strictEqual(reqs[1].updateCells.rows[0].values[0].userEnteredValue.numberValue, 3, 'Total numeric');

// New date not in colA: append after last dated row (index 4 -> 5), stamping the date.
out = buildPivotItems(items({
  operation: 'append', display_employee: 'Ivan', Date: '06/16/2026', Time_in: '6:22 PM',
}), colA);
reqs = out[0].json.body.requests;
assert.strictEqual(reqs.length, 2, 'new date -> date cell + in cell');
assert.strictEqual(reqs[0].updateCells.range.startRowIndex, 5, 'append at index 5');
assert.strictEqual(reqs[0].updateCells.range.startColumnIndex, 0, 'writes Date col');
assert.strictEqual(reqs[0].updateCells.rows[0].values[0].userEnteredValue.stringValue, '06/16/2026');
assert.strictEqual(reqs[1].updateCells.range.startColumnIndex, 1, 'then Ivan In');

// Nae -> skipped (manual columns).
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Nae', Date: '05/04/2026', Time_in: '6:00 PM' }), colA).length,
  0, 'Nae -> no writes');

// Unknown employee -> skipped.
assert.strictEqual(
  buildPivotItems(items({ operation: 'append', display_employee: 'Unknown (999)', Date: '05/04/2026', Time_in: '6:00 PM' }), colA).length,
  0, 'unknown -> no writes');

console.log('ALL PIVOT TESTS PASSED');
