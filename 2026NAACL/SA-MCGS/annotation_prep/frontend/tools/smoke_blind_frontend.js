#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const frontend = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(frontend, 'data', 'manifest.json'), 'utf8'));
const translations = JSON.parse(fs.readFileSync(path.join(frontend, 'data', 'translations_zh.json'), 'utf8'));
const source = fs.readFileSync(path.join(frontend, 'blind_app.js'), 'utf8');
const prefix = source.split('// BOOTSTRAP_BINDINGS')[0];
assert.notEqual(prefix, source, 'Missing test boundary in blind_app.js');

const localData = new Map();
const elements = {
  saveStatus: { textContent: '' },
  saveIndicator: { classList: { add() {}, remove() {} } },
  toast: { textContent: '', classList: { add() {}, remove() {}, toggle() {} } },
};
const sandbox = {
  console,
  Blob,
  URL,
  setTimeout,
  clearTimeout,
  document: {
    getElementById(id) { return elements[id] || null; },
    createElement() { return {}; },
    body: { appendChild() {} },
  },
  localStorage: {
    getItem(key) { return localData.has(key) ? localData.get(key) : null; },
    setItem(key, value) { localData.set(key, String(value)); },
  },
  window: {
    confirm() { return true; },
    scrollTo() {},
  },
};
vm.createContext(sandbox);
vm.runInContext(`${prefix}\n;globalThis.__api = { state, validateData, isComplete, buildExportRows, saveState, loadStoredState, spreadsheetSafe, xlsxSafeRows, validateCurrentCase };`, sandbox);
const api = sandbox.__api;

api.validateData(manifest, translations);
api.state.manifest = manifest;
api.state.translations = translations;
api.state.cases = manifest.cases;
api.state.activeExpert = 'expert_1';
api.state.orders = Object.fromEntries(Object.entries(manifest.expert_orders).map(([key, value]) => [key, [...value]]));
api.state.reviewerIds = { expert_1: 'E01' };
api.state.annotations = { expert_1: {} };

const byId = new Map(manifest.cases.map((item) => [item.presentation_id, item]));
for (const presentationId of manifest.expert_orders.expert_1) {
  const item = byId.get(presentationId);
  const sections = {};
  item.sections.forEach((section, index) => {
    sections[section.section_id] = {
      role: index === 0 ? 'conflict_evidence' : 'ordinary_context',
      role_label: index === 0 ? '核心冲突证据' : '一般上下文',
      minimal_evidence: index === 0,
      repair_packet: index === 0,
      note: index === 0 ? '=formula-like note' : '',
    };
  });
  api.state.annotations.expert_1[presentationId] = {
    reviewer_id: 'E01',
    expert_slot: 'expert_1',
    target_conflict: 'present',
    evidence_sufficient: 'yes',
    need_more_context: 'no',
    confidence: '4',
    comments: '@formula-like note',
    sections,
    saved_at: '2026-09-05T00:00:00.000Z',
  };
}

assert.equal(manifest.expert_orders.expert_1.every((id) => api.isComplete(id)), true);
const rows = api.buildExportRows('expert_1');
assert.equal(rows.caseRows.length, 42);
assert.equal(rows.sectionRows.length, 648);
const forbiddenColumns = /condition|method|model|hint|pre|post|injection|ground.?truth|reference.?answer/i;
for (const row of [...rows.caseRows, ...rows.sectionRows]) {
  assert.equal(Object.keys(row).some((key) => forbiddenColumns.test(key)), false);
}
assert.equal(api.spreadsheetSafe('=1+1'), "'=1+1");
assert.equal(api.xlsxSafeRows([{ note: '@unsafe', count: 1 }])[0].note, "'@unsafe");

api.state.activeIndex = 11;
api.state.activeIndices = { expert_1: 11 };
assert.equal(api.saveState('smoke'), true);
api.state.annotations = {};
api.state.reviewerIds = {};
api.state.activeIndices = {};
api.loadStoredState();
assert.equal(api.state.activeIndex, 11);
assert.equal(Object.keys(api.state.annotations.expert_1).length, 42);
assert.equal(api.validateCurrentCase().valid, true);

const XLSX = require(path.join(frontend, 'vendor', 'xlsx.full.min.js'));
const workbook = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(api.xlsxSafeRows(rows.caseRows)), 'cases');
XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(api.xlsxSafeRows(rows.sectionRows)), 'sections');
const bytes = XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' });
const roundTrip = XLSX.read(bytes, { type: 'buffer' });
assert.deepEqual(roundTrip.SheetNames, ['cases', 'sections']);
assert.equal(XLSX.utils.sheet_to_json(roundTrip.Sheets.cases).length, 42);
assert.equal(XLSX.utils.sheet_to_json(roundTrip.Sheets.sections).length, 648);

console.log('blind frontend smoke: pass');
console.log('cases=42 sections=648 current-expert-only export=pass resume=pass xlsx=pass');
