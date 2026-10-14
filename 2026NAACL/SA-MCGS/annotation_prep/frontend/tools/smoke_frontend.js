#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');

const frontend = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(frontend, 'app.js'), 'utf8');
const bindingMarker = "$('loadManifestBtn').addEventListener";
assert.ok(appSource.includes(bindingMarker), 'could not locate app bootstrap marker');
const librarySource = appSource.slice(0, appSource.indexOf(bindingMarker));
const manifest = JSON.parse(fs.readFileSync(path.join(frontend, 'data', 'manifest.json'), 'utf8'));
const translations = JSON.parse(fs.readFileSync(path.join(frontend, 'data', 'translations_zh.json'), 'utf8'));
const hints = JSON.parse(fs.readFileSync(path.join(frontend, 'data', 'method_hints.json'), 'utf8'));

const storage = new Map();
const fakeElement = () => ({
  textContent: '',
  value: '',
  style: {},
  classList: { add() {} },
  querySelector() { return null; },
  querySelectorAll() { return []; },
});
const elements = new Map();
const documentMock = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, fakeElement());
    return elements.get(id);
  },
  querySelector() { return fakeElement(); },
  querySelectorAll() { return []; },
};
const context = vm.createContext({
  console,
  document: documentMock,
  window: {},
  localStorage: {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, String(value)); },
    removeItem(key) { storage.delete(key); },
  },
  setTimeout,
  clearTimeout,
  Blob,
  URL,
});
vm.runInContext(librarySource, context, { filename: 'app.js' });

const result = vm.runInContext(`
  (() => {
    const checked = validateManifest(${JSON.stringify(manifest)});
    const checkedTranslations = ${JSON.stringify(translations)};
    const checkedHints = ${JSON.stringify(hints)};
    validateAuxiliaryPacks(checked, checkedTranslations, checkedHints);
    state.manifest = checked;
    state.translations = checkedTranslations;
    state.hints = checkedHints;
    state.cases = checked.cases;
    state.activeExpert = 'expert_1';
    state.annotations = {};
    state.reviewerIds = {};
    state.orders = {};
    loadStoredState();
    const freshFirstLoadCount = casesForActiveExpert().length;
    state.annotations = {
      expert_1: {
        [checked.cases[0].presentation_id]: {
          reviewer_id: 'E01',
          expert_slot: 'expert_1',
          expert_label: '专家 1',
          overall_conflict: 'no',
          material_sufficient: 'not_applicable',
          need_more_context: 'no',
          confidence: '4',
          comments: 'smoke',
          sections: Object.fromEntries(checked.cases[0].sections.map((section) => [section.section_id, {
              judgement: 'clear',
              judgement_label: '没有明显问题',
              keep_for_repair: false,
              note: ''
            }])),
          saved_at: '2026-08-29T00:00:00.000Z'
        }
      }
    };
    state.reviewerIds = { expert_1: 'E01' };
    state.orders = checked.expert_orders;
    saveState('smoke save');
    const storedBeforeReset = JSON.parse(localStorage.getItem(manifestKey()));
    state.annotations = {};
    state.reviewerIds = {};
    state.orders = {};
    loadStoredState();
    const resumed = annotationFor(checked.cases[0].presentation_id, 'expert_1');
    const exported = buildExport();
    return {
      storedSchema: storedBeforeReset.schema_version,
      resumedConflict: resumed.overall_conflict,
      resumedMaterial: resumed.material_sufficient,
      caseRows: exported.caseRows.length,
      sectionRows: exported.sectionRows.length,
      expectedCaseRows: checked.cases.length * 3,
      expectedSectionRows: checked.cases.reduce((sum, item) => sum + item.sections.length, 0) * 3,
      complete: isComplete(checked.cases[0].presentation_id, 'expert_1'),
      freshFirstLoadCount,
      legacyCaseColumn: exported.caseRows[0]['样本编号'],
      legacySectionColumn: exported.sectionRows[0]['原始编号'],
      annotationMode: exported.caseRows[0]['标注模式'],
      chineseText: exported.sectionRows[0]['中文正文'],
      leaHint: exported.sectionRows[0]['LEA提示'],
      saHint: exported.sectionRows[0]['SA_MCGS提示'],
      paragraphHtml: renderParagraph(checked.cases[0], checked.cases[0].sections[0], 0),
      nextParagraphHtml: renderParagraph(checked.cases[0], checked.cases[0].sections[1], 1),
      firstSectionId: checked.cases[0].sections[0].section_id,
      nextSectionId: checked.cases[0].sections[1].section_id,
    };
  })()
`, context);

assert.equal(result.storedSchema, 'assisted_annotation.state.v1');
assert.equal(result.resumedConflict, 'no');
assert.equal(result.resumedMaterial, 'not_applicable');
assert.equal(result.complete, true);
assert.equal(result.freshFirstLoadCount, manifest.cases.length);
assert.ok(result.legacyCaseColumn.startsWith('P-'));
assert.ok(result.legacySectionColumn.startsWith('S'));
assert.equal(result.annotationMode, '算法辅助复核');
assert.ok(result.chineseText.length > 0);
assert.ok(result.leaHint.includes('models'));
assert.ok(result.saHint.includes('models'));
const firstRadioName = `name="section_judgement_${result.firstSectionId}"`;
const nextRadioName = `name="section_judgement_${result.nextSectionId}"`;
assert.equal(result.paragraphHtml.split(firstRadioName).length - 1, 4);
assert.equal(result.nextParagraphHtml.split(nextRadioName).length - 1, 4);
assert.ok(!result.paragraphHtml.includes(nextRadioName));
assert.equal(result.caseRows, result.expectedCaseRows);
assert.equal(result.sectionRows, result.expectedSectionRows);

const XLSX = require(path.join(frontend, 'vendor', 'xlsx.full.min.js'));
const workbook = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet([{ status: 'ok' }]), '样本整体标注');
XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet([{ status: 'ok' }]), '逐段标注');
const tempFile = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'assisted-audit-smoke-')), 'export.xlsx');
const binary = XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' });
fs.writeFileSync(tempFile, binary);
const reopened = XLSX.read(fs.readFileSync(tempFile), { type: 'buffer' });
assert.deepEqual(reopened.SheetNames, ['样本整体标注', '逐段标注']);

console.log('FRONTEND SMOKE TEST PASSED');
console.log(`- manifest presentations: ${manifest.cases.length}`);
console.log('- localStorage save/resume: passed');
console.log('- negative-case not_applicable: passed');
console.log('- Chinese translation + LEA/SA-MCGS hints: passed');
console.log('- per-section radio mutual-exclusion groups: passed');
console.log(`- export rows: ${result.caseRows} case / ${result.sectionRows} section`);
console.log('- XLSX write/read with two sheets: passed');
