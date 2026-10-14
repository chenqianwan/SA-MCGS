#!/usr/bin/env node
'use strict';

// This test never opens the browser's storage or writes annotation files.
// All annotations, storage, downloads, and spreadsheet bytes stay in memory.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const frontend = path.resolve(__dirname, '..');
const htmlPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(frontend, '..', 'dist', 'sa_mcgs_blind_annotation.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const scriptTags = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)];
const embedded = new Map();
for (const [, attributes, contents] of scriptTags) {
  const id = attributes.match(/\bid\s*=\s*["']([^"']+)["']/i)?.[1];
  if (id) embedded.set(id, contents);
  assert.equal(/\bsrc\s*=/i.test(attributes), false, 'Standalone page must not load external scripts');
}
for (const id of ['manifestData', 'translationData', 'methodHintsData']) {
  assert.ok(embedded.has(id), `Missing embedded ${id}`);
}
const manifest = JSON.parse(embedded.get('manifestData'));
const translations = JSON.parse(embedded.get('translationData'));
const hints = JSON.parse(embedded.get('methodHintsData'));
const previousHintHashes = hints.previous_hint_pack_hashes || [];
assert.ok(previousHintHashes.length > 0, 'Updated snapshot must declare compatible previous hint packs');
const historyDirectory = path.join(frontend, 'data', 'history');
const historicalPacks = fs.readdirSync(historyDirectory)
  .filter((name) => name.endsWith('.json'))
  .map((name) => JSON.parse(fs.readFileSync(path.join(historyDirectory, name), 'utf8')));
const oldHints = historicalPacks.find((pack) => previousHintHashes.includes(pack.hint_pack_hash));
assert.ok(oldHints, 'A compatible previous hint pack must remain available for regression comparison');
const appScripts = scriptTags.map(([, , contents]) => contents).filter((contents) => contents.includes('// BOOTSTRAP_BINDINGS'));
assert.equal(appScripts.length, 1, 'Expected exactly one application script');
const appPrefix = appScripts[0].split('// BOOTSTRAP_BINDINGS')[0];
assert.equal(/\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\s*\(/.test(appPrefix), false, 'Application must remain offline');
assert.match(html, /id=["']toggleHintsBtn["']/);

const clone = (value) => JSON.parse(JSON.stringify(value));
const storedData = new Map();
const elements = new Map();
const downloads = [];
const workbooks = [];
function fakeElement() {
  const classes = new Set();
  return {
    textContent: '', innerHTML: '', value: '', hidden: false, style: {}, dataset: {},
    classList: {
      add(...values) { values.forEach((value) => classes.add(value)); },
      remove(...values) { values.forEach((value) => classes.delete(value)); },
      contains(value) { return classes.has(value); },
      toggle(value, force) {
        const selected = force === undefined ? !classes.has(value) : Boolean(force);
        if (selected) classes.add(value); else classes.delete(value);
        return selected;
      },
    },
    addEventListener() {},
    setAttribute(name, value) { this[name] = String(value); },
    getAttribute(name) { return this[name] ?? null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    insertAdjacentHTML(_where, value) { this.innerHTML += value; },
    click() {}, remove() {},
  };
}
const documentMock = {
  getElementById(id) {
    if (!elements.has(id)) {
      const element = fakeElement();
      if (embedded.has(id)) element.textContent = embedded.get(id);
      if (id === 'workspace') {
        element.querySelector = (selector) => selector === '.case-meta'
          ? { insertAdjacentHTML(_where, value) { element.innerHTML += value; } }
          : null;
      }
      elements.set(id, element);
    }
    return elements.get(id);
  },
  createElement() { return fakeElement(); },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  body: fakeElement(),
};
const realXlsx = require(path.join(frontend, 'vendor', 'xlsx.full.min.js'));
const xlsxMock = {
  ...realXlsx,
  writeFile(workbook, filename) {
    const bytes = realXlsx.write(workbook, { type: 'buffer', bookType: 'xlsx' });
    workbooks.push({ filename, workbook: realXlsx.read(bytes, { type: 'buffer' }) });
  },
};
const sandbox = {
  console,
  Blob,
  URL,
  document: documentMock,
  localStorage: {
    getItem(key) { return storedData.has(key) ? storedData.get(key) : null; },
    setItem(key, value) { storedData.set(key, String(value)); },
    removeItem(key) { storedData.delete(key); },
  },
  window: { confirm() { return true; }, scrollTo() {}, XLSX: xlsxMock },
  XLSX: xlsxMock,
  setTimeout() { return 0; },
  clearTimeout() {},
  __captureDownload(filename, content, mimeType) { downloads.push({ filename, content, mimeType }); },
};
vm.createContext(sandbox);
vm.runInContext(`${appPrefix}\n
  globalThis.__api = {
    state, validateData, validateHints, initializeAssistedHints, toggleHints,
    storeKey, saveState, loadStoredState, buildExportRows, restoreBackup,
    exportJson, exportCsv, exportXlsx, renderParagraph, renderWorkspace,
    renderModelHint, renderAlgorithmHints, isComplete, validateCurrentCase,
  };
  downloadBlob = (filename, content, mimeType) => __captureDownload(filename, content, mimeType);
  captureCurrentForm = () => {};
  renderAll = () => {};
`, sandbox, { filename: htmlPath });
const api = sandbox.__api;

function resetInMemoryState() {
  api.state.manifest = clone(manifest);
  api.state.translations = clone(translations);
  api.state.cases = api.state.manifest.cases;
  api.state.activeExpert = 'expert_1';
  api.state.activeIndex = 0;
  api.state.activeIndices = {};
  api.state.annotations = {};
  api.state.reviewerIds = {};
  api.state.orders = clone(manifest.expert_orders);
  api.state.hintsVisible = true;
  api.state.hintPackHistory = [];
  api.state.progressOrigin = 'new_assisted_session';
  api.initializeAssistedHints();
}

function syntheticAnnotations(expertId = 'expert_1') {
  return Object.fromEntries(manifest.cases.map((item) => [item.presentation_id, {
    reviewer_id: `TEST-ONLY-${expertId}`, expert_slot: expertId,
    target_conflict: 'present', evidence_sufficient: 'yes',
    need_more_context: 'no', confidence: '4', comments: '@synthetic-only',
    sections: Object.fromEntries(item.sections.map((section, index) => [section.section_id, {
      role: index === 0 ? 'conflict_evidence' : 'ordinary_context',
      minimal_evidence: index === 0, repair_packet: index === 0,
      note: index === 0 ? '=synthetic-only' : '',
    }])),
    saved_at: '2000-01-01T00:00:00.000Z',
  }]));
}

function classCount(markup, expected) {
  return [...markup.matchAll(/\bclass=["']([^"']*)["']/g)]
    .filter(([, names]) => names.split(/\s+/).includes(expected)).length;
}

function assertHintHistory(raw, expectedHashes = [hints.hint_pack_hash]) {
  const history = typeof raw === 'string'
    ? (raw.trim().startsWith('[') ? JSON.parse(raw) : raw.split(';').filter(Boolean))
    : clone(raw);
  assert.ok(Array.isArray(history), 'Hint history must be an array or an encoded list');
  assert.equal(new Set(history).size, history.length, 'Hint history must not contain duplicate hashes');
  for (const hash of expectedHashes) assert.ok(history.includes(hash), `Hint history lost ${hash}`);
}

function verifyRefreshedHints() {
  const screenshotCase = hints.cases['P-1FB71850B0'];
  assert.equal(screenshotCase.condition, 'pre');
  for (const model of ['gpt-4o', 'gemini-2.5-pro']) {
    assert.equal(screenshotCase.sections.S003.methods['sa-mcgs'].models[model].status, 'available', `Screenshot regression: ${model}`);
  }
  const preCases = Object.values(hints.cases).filter((item) => item.condition === 'pre');
  assert.equal(preCases.length, 18);
  for (const [model, expectedAvailable] of [['gpt-4o', 15], ['gemini-2.5-pro', 18]]) {
    let available = 0;
    for (const item of preCases) {
      const statuses = new Set(Object.values(item.sections).map((section) => section.methods['sa-mcgs'].models[model].status));
      assert.equal(statuses.size, 1, 'Each model run must have one consistent validity status across all paragraphs');
      if (statuses.has('available')) available += 1;
    }
    assert.equal(available, expectedAvailable, `${model}: repaired pre SA validity`);
  }
  let unchangedPost = 0;
  for (const [presentationId, previous] of Object.entries(oldHints.cases)) {
    const current = hints.cases[presentationId];
    if (previous.condition === 'post') {
      assert.deepEqual(current, previous, `${presentationId}: unrelated post hints must remain unchanged`);
      unchangedPost += 1;
    } else {
      for (const [sectionId, oldSection] of Object.entries(previous.sections)) {
        for (const [model, oldHint] of Object.entries(oldSection.methods.lea.models)) {
          const newHint = current.sections[sectionId].methods.lea.models[model];
          if (oldHint.status === 'available') {
            assert.deepEqual(newHint, oldHint, `${presentationId}/${sectionId}/${model}: LEA success hint changed`);
          } else {
            assert.equal(newHint.status, oldHint.status, 'LEA validity must not change in the SA refresh');
            assert.deepEqual({ ...newHint, reason_zh: '' }, { ...oldHint, reason_zh: '' }, 'Only invalid-reason wording may change for existing LEA failures');
          }
        }
      }
    }
  }
  assert.equal(unchangedPost, 24);
}

async function main() {
  verifyRefreshedHints();
  resetInMemoryState();
  api.validateData(api.state.manifest, api.state.translations);
  api.validateHints(api.state.manifest, api.state.hints);
  assert.equal(api.state.hintsVisible, true, 'Hints should be shown by default');
  assert.equal(manifest.cases.length, 42);
  assert.equal(manifest.cases.reduce((sum, item) => sum + item.sections.length, 0), 648);
  const badHints = { ...clone(hints), source_manifest_hash: 'wrong-manifest' };
  assert.throws(() => api.validateHints(manifest, badHints), /版本|一致|匹配|样本|manifest/i);

  let paragraphCount = 0;
  for (const item of api.state.cases) {
    for (const [index, section] of item.sections.entries()) {
      const rendered = api.renderParagraph(item, section, index);
      assert.equal(classCount(rendered, 'algorithm-hints'), 1, `${item.presentation_id}/${section.section_id}: hints panel`);
      assert.equal(classCount(rendered, 'model-hint'), 4, `${item.presentation_id}/${section.section_id}: four method/model results`);
      assert.match(rendered, /LEA/);
      assert.match(rendered, /SA-MCGS/);
      assert.match(rendered, /GPT-4o/i);
      assert.match(rendered, /Gemini/i);
      assert.equal((rendered.match(new RegExp(`name="section_role_${section.section_id}"`, 'g')) || []).length, 4);
      paragraphCount += 1;
    }
  }
  assert.equal(paragraphCount, 648);
  const availableHint = api.renderModelHint('gpt-4o', {
    status: 'available', selected: true, score: 0.4321, rank: 2, total_nodes: 11,
    top3: true, conflict_endpoint_mentions: 3, local_evidence_mentions: 2, repair_entry_mentions: 1,
  });
  assert.match(availableHint, /0\.432/);
  assert.match(availableHint, /选|保留|纳入/);
  assert.match(availableHint, /排名|名次|第\s*2/);
  const invalidHint = api.renderModelHint('gpt-4o', { status: 'strict_invalid', reason_zh: '输出未通过严格校验' });
  assert.match(invalidHint, /未通过严格校验/);
  assert.doesNotMatch(invalidHint, /0\.0000|未选入/);
  const escapedHint = api.renderModelHint('gpt-4o', { status: 'missing', reason_zh: '<img src=x onerror=alert(1)>' });
  assert.doesNotMatch(escapedHint, /<img\b/);
  assert.match(escapedHint, /&lt;img/);

  for (const condition of ['pre', 'post']) {
    const item = api.state.cases.find((candidate) => hints.cases[candidate.presentation_id].condition === condition);
    assert.ok(item, `No ${condition} sample`);
    api.state.activeIndex = api.state.orders.expert_1.indexOf(item.presentation_id);
    api.renderWorkspace();
    const markup = elements.get('workspace').innerHTML;
    assert.ok(classCount(markup, 'sample-condition') >= 1, 'Sample should identify pre/post condition');
    assert.match(markup, condition === 'pre' ? /注入前|未注入/ : /注入后/);
  }

  const legacyKey = `sa_mcgs_blind_expert_audit_v2:${manifest.study_id}:${manifest.manifest_hash}`;
  const legacyPayload = {
    schema_version: 'blind_annotation.state.v2', annotation_mode: 'blind_human_audit',
    study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
    translation_pack_hash: translations.translation_pack_hash,
    active_expert: 'expert_1', active_indices: { expert_1: 11 },
    annotations: { expert_1: syntheticAnnotations() },
    reviewer_ids: { expert_1: 'TEST-ONLY-E01' }, orders: clone(manifest.expert_orders),
    created_at: '2000-01-01T00:00:00.000Z',
  };
  const legacyRaw = JSON.stringify(legacyPayload);
  storedData.clear();
  storedData.set(legacyKey, legacyRaw);
  resetInMemoryState();
  api.loadStoredState();
  assert.equal(api.state.activeIndex, 11, 'Migration should preserve active sample');
  assert.equal(Object.keys(api.state.annotations.expert_1).length, 42);
  assert.equal(storedData.get(legacyKey), legacyRaw, 'Migration must not overwrite old blind storage');
  assert.notEqual(api.storeKey(), legacyKey);
  assert.match(api.storeKey(), /sa_mcgs_assisted_expert_audit_v1/);
  assert.ok(api.storeKey().includes(hints.hint_pack_hash), 'Assisted state is pinned to the hints version');
  assert.equal(api.saveState('synthetic smoke'), true);
  const saved = JSON.parse(storedData.get(api.storeKey()));
  assert.equal(saved.schema_version, 'assisted_standalone_annotation.state.v1');
  assert.equal(saved.annotation_mode, 'method_assisted_review');
  assert.equal(saved.hint_pack_hash, hints.hint_pack_hash);
  assert.equal(saved.hints_visible, true);
  assertHintHistory(saved.hint_pack_history);
  assert.ok(saved.progress_origin, 'Copied progress must record its origin');
  assert.equal(api.state.orders.expert_1.every((id) => api.isComplete(id)), true);
  assert.equal(api.validateCurrentCase().valid, true);

  api.state.reviewerIds.expert_1 = 'TEST-ONLY-ASSISTED';
  api.saveState();
  resetInMemoryState();
  api.loadStoredState();
  assert.equal(api.state.reviewerIds.expert_1, 'TEST-ONLY-ASSISTED', 'An existing assisted state must take precedence over old blind state');
  assert.equal(storedData.get(legacyKey), legacyRaw);

  api.toggleHints();
  assert.equal(api.state.hintsVisible, false);
  api.saveState();
  const hiddenState = JSON.parse(storedData.get(api.storeKey()));
  assert.equal(hiddenState.annotation_mode, 'method_assisted_review', 'Hiding hints must not relabel results as blind');
  assert.equal(hiddenState.hints_visible, false);
  api.toggleHints();
  assert.equal(api.state.hintsVisible, true);

  const rows = api.buildExportRows();
  assert.equal(rows.caseRows.length, 42);
  assert.equal(rows.sectionRows.length, 648);
  for (const row of [...rows.caseRows, ...rows.sectionRows]) {
    assert.equal(row.annotation_mode, 'method_assisted_review');
    assert.equal(row.hint_pack_hash, hints.hint_pack_hash);
    assertHintHistory(row.hint_pack_history);
  }
  api.exportJson();
  const backup = JSON.parse(downloads.at(-1).content);
  assert.equal(backup.schema_version, 'assisted_standalone_annotation.export.v1');
  assert.equal(backup.annotation_mode, 'method_assisted_review');
  assert.equal(backup.hint_pack_hash, hints.hint_pack_hash);
  assert.equal(Object.keys(backup.annotations).length, 42);
  assert.ok(backup.progress_origin);
  assertHintHistory(backup.hint_pack_history);

  api.exportCsv();
  const csv = downloads.at(-1).content;
  assert.match(csv, /annotation_mode/);
  assert.match(csv, /hint_pack_hash/);
  assert.match(csv, /hint_pack_history/);
  assert.match(csv, /method_assisted_review/);
  assert.ok(csv.includes(hints.hint_pack_hash));
  assert.match(csv, /'@synthetic-only/, 'CSV cells must escape formula-like notes');
  api.exportXlsx();
  assert.equal(workbooks.length, 1);
  const workbook = workbooks[0].workbook;
  assert.deepEqual(workbook.SheetNames, ['样本整体标注', '逐段标注', '版本信息']);
  for (const name of ['样本整体标注', '逐段标注', '版本信息']) {
    const sheetRows = realXlsx.utils.sheet_to_json(workbook.Sheets[name]);
    assert.equal(sheetRows[0].annotation_mode, 'method_assisted_review', `${name}: assisted mode`);
    assert.equal(sheetRows[0].hint_pack_hash, hints.hint_pack_hash, `${name}: hints provenance`);
    assertHintHistory(sheetRows[0].hint_pack_history);
  }
  assert.equal(realXlsx.utils.sheet_to_json(workbook.Sheets['样本整体标注']).length, 42);
  assert.equal(realXlsx.utils.sheet_to_json(workbook.Sheets['逐段标注']).length, 648);

  const legacyBackup = {
    ...backup, schema_version: 'blind_annotation.export.v2', annotation_mode: 'blind_human_audit',
    anonymous_reviewer_id: 'TEST-ONLY-IMPORTED-BLIND', active_index: 3,
  };
  delete legacyBackup.hint_pack_hash;
  delete legacyBackup.progress_origin;
  await api.restoreBackup(legacyBackup);
  assert.equal(api.state.activeIndex, 3);
  assert.equal(api.state.reviewerIds.expert_1, 'TEST-ONLY-IMPORTED-BLIND');
  api.exportJson();
  const importedExport = JSON.parse(downloads.at(-1).content);
  assert.equal(importedExport.schema_version, 'assisted_standalone_annotation.export.v1');
  assert.equal(importedExport.annotation_mode, 'method_assisted_review');
  assert.equal(importedExport.hint_pack_hash, hints.hint_pack_hash);
  assert.equal(importedExport.progress_origin, 'copied_from_blind_json_backup');
  assert.equal(storedData.get(legacyKey), legacyRaw, 'Import must not mutate the old blind store');
  await assert.rejects(api.restoreBackup({ ...backup, hint_pack_hash: 'wrong-hint-pack' }), /版本|一致|匹配|提示/i);
  await assert.rejects(api.restoreBackup({ ...legacyBackup, manifest_hash: 'wrong-manifest' }), /版本|一致|匹配|样本/i);
  const beforeCancelledRestore = JSON.stringify(api.state);
  const storedBeforeCancelledRestore = storedData.get(api.storeKey());
  sandbox.window.confirm = () => false;
  await api.restoreBackup({ ...backup, anonymous_reviewer_id: 'CANCELLED-DO-NOT-APPLY' });
  sandbox.window.confirm = () => true;
  assert.equal(JSON.stringify(api.state), beforeCancelledRestore, 'Cancelled restore must not change progress or provenance');
  assert.equal(storedData.get(api.storeKey()), storedBeforeCancelledRestore);

  // A legacy state with different translated material must not be silently copied.
  storedData.clear();
  const incompatibleLegacy = JSON.stringify({ ...legacyPayload, translation_pack_hash: 'wrong-translation' });
  storedData.set(legacyKey, incompatibleLegacy);
  resetInMemoryState();
  assert.throws(() => api.loadStoredState(), /进度|版本|不匹配/);
  assert.equal(Object.keys(api.state.annotations.expert_1 || {}).length, 0);
  assert.equal(storedData.get(legacyKey), incompatibleLegacy);

  // The new snapshot copies a compatible old assisted session before considering
  // blind-state fallback, preserving every expert's labels and the old key.
  const oldAssistedKey = `sa_mcgs_assisted_expert_audit_v1:${manifest.study_id}:${manifest.manifest_hash}:${oldHints.hint_pack_hash}`;
  const oldAssistedPayload = {
    ...legacyPayload,
    schema_version: 'assisted_standalone_annotation.state.v1', annotation_mode: 'method_assisted_review',
    hint_pack_hash: oldHints.hint_pack_hash, hints_visible: false,
    progress_origin: 'copied_from_blind_local_storage',
    active_expert: 'expert_3', active_indices: { expert_1: 11, expert_2: 19, expert_3: 8 },
    annotations: Object.fromEntries(['expert_1', 'expert_2', 'expert_3'].map((expertId) => [expertId, syntheticAnnotations(expertId)])),
    reviewer_ids: { expert_1: 'OLD-ASSISTED-1', expert_2: 'OLD-ASSISTED-2', expert_3: 'OLD-ASSISTED-3' },
  };
  const oldAssistedRaw = JSON.stringify(oldAssistedPayload);
  storedData.clear();
  storedData.set(legacyKey, legacyRaw);
  storedData.set(oldAssistedKey, oldAssistedRaw);
  resetInMemoryState();
  api.loadStoredState();
  assert.equal(api.state.activeExpert, 'expert_3');
  assert.equal(api.state.activeIndex, 8);
  assert.equal(api.state.hintsVisible, false);
  assert.deepEqual(clone(api.state.annotations), oldAssistedPayload.annotations);
  assert.deepEqual(clone(api.state.reviewerIds), oldAssistedPayload.reviewer_ids);
  assert.deepEqual(clone(api.state.orders), oldAssistedPayload.orders);
  assert.equal(storedData.get(oldAssistedKey), oldAssistedRaw);
  assert.equal(storedData.get(legacyKey), legacyRaw);
  assertHintHistory(api.state.hintPackHistory, [oldHints.hint_pack_hash, hints.hint_pack_hash]);
  api.saveState();
  assertHintHistory(JSON.parse(storedData.get(api.storeKey())).hint_pack_history, [oldHints.hint_pack_hash, hints.hint_pack_hash]);
  api.exportJson();
  const migratedBackup = JSON.parse(downloads.at(-1).content);
  assert.deepEqual(migratedBackup.annotations, oldAssistedPayload.annotations.expert_3);
  assertHintHistory(migratedBackup.hint_pack_history, [oldHints.hint_pack_hash, hints.hint_pack_hash]);

  const oldAssistedBackup = {
    ...backup, hint_pack_hash: oldHints.hint_pack_hash,
    annotations: syntheticAnnotations('expert_1'),
    anonymous_reviewer_id: 'OLD-ASSISTED-JSON', active_index: 7,
  };
  // Historical exports did not contain hint_pack_history; compatibility must
  // derive it from the declared old hint hash rather than erase the provenance.
  delete oldAssistedBackup.hint_pack_history;
  await api.restoreBackup(oldAssistedBackup);
  assert.equal(api.state.activeExpert, 'expert_1');
  assert.equal(api.state.activeIndex, 7);
  assert.deepEqual(clone(api.state.annotations.expert_1), oldAssistedBackup.annotations);
  assert.deepEqual(clone(api.state.annotations.expert_2), oldAssistedPayload.annotations.expert_2);
  assert.deepEqual(clone(api.state.annotations.expert_3), oldAssistedPayload.annotations.expert_3);
  api.exportJson();
  const migratedJsonExport = JSON.parse(downloads.at(-1).content);
  assert.equal(migratedJsonExport.hint_pack_hash, hints.hint_pack_hash);
  assertHintHistory(migratedJsonExport.hint_pack_history, [oldHints.hint_pack_hash, hints.hint_pack_hash]);
  assert.equal(storedData.get(oldAssistedKey), oldAssistedRaw);
  assert.equal(storedData.get(legacyKey), legacyRaw);
  for (const row of Object.values(api.buildExportRows()).flat()) {
    assertHintHistory(row.hint_pack_history, [oldHints.hint_pack_hash, hints.hint_pack_hash]);
  }
  const beforeUnknownImport = JSON.stringify(api.state);
  await assert.rejects(api.restoreBackup({ ...oldAssistedBackup, hint_pack_hash: `sha256:${'0'.repeat(64)}` }), /版本|一致|匹配|提示/i);
  assert.equal(JSON.stringify(api.state), beforeUnknownImport);

  // A known storage key is not sufficient if the content declares another hash.
  storedData.clear();
  const wrongHashState = JSON.stringify({ ...oldAssistedPayload, hint_pack_hash: `sha256:${'0'.repeat(64)}` });
  storedData.set(oldAssistedKey, wrongHashState);
  resetInMemoryState();
  assert.throws(() => api.loadStoredState(), /版本|一致|匹配|提示|进度/i);
  assert.equal(storedData.get(oldAssistedKey), wrongHashState);
  assert.equal(Object.keys(api.state.annotations).length, 0);

  console.log('assisted standalone smoke: pass');
  console.log('42 presentations / 648 paragraphs / 2,592 method-model hints; pre/post labels: pass');
  console.log('offline embedding; old blind-state preservation; migration/import; isolated assisted resume: pass');
  console.log('hint visibility never changes annotation mode; JSON/CSV/XLSX provenance and safety: pass');
  console.log('September retry hints: GPT-4o 15/18, Gemini 18/18; screenshot case and frozen post hints: pass');
  console.log('old assisted storage/JSON migration preserves labels, original records and hint history: pass');
  console.log('All test annotations, storage, downloads, and workbooks remained in memory.');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
