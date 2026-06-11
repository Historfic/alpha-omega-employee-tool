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
