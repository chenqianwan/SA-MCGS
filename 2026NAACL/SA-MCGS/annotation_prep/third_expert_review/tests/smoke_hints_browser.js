#!/usr/bin/env node
'use strict';

// Run only in a disposable browser context; all responses below are synthetic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, 'dist', '第三专家_独立盲评.html');
const blindPath = path.join(root, 'dist', '第三专家_独立盲评.original.html');
const load = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const clone = (v) => JSON.parse(JSON.stringify(v));
const stable = (v) => { const out = clone(v); delete out.exported_at; return out; };
const html = fs.readFileSync(htmlPath, 'utf8');
const embedded = (source, id) => {
  const match = source.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`));
  assert.ok(match, `Missing embedded ${id}`);
  return JSON.parse(match[1]);
};
const embed = (id) => embedded(html, id);
const manifest = load(path.join(root, 'data/manifest.json'));
const translations = load(path.join(root, 'data/translations_zh.json'));
const sourceHints = load(path.join(root, '../frontend/data/method_hints.json'));
const hints = embed('methodHintsData');
const markers = embed('injectionMarkersData');
const sourceMarkers = embedded(fs.readFileSync(path.join(root, '../dist/sa_mcgs_blind_annotation.html'), 'utf8'), 'injectionMarkersData');
const markerFields = ['injection_marker_pack_hash', 'injection_hints_visible', 'injection_hints_displayed'];
const oldStorageKey = `sa-mcgs:third-expert:${manifest.study_id}:${manifest.manifest_hash}:binary_judgment_v1:expert_3`;
const first = manifest.cases[0];
const conditionCounts = { pre: 0, post: 0 };
let markedParagraphs = 0;

function legacyRecord(item, complete = true) {
  return { annotation_protocol: 'binary_judgment_v1', review_protocol: 'targeted_third_blind_v1',
    expert_slot: 'expert_3', reviewer_id: 'TEST-ONLY-LEGACY3', target_conflict: complete ? 'present' : '',
    judgment_sufficient: complete ? 'yes' : '', confidence: complete ? '4' : '', comments: 'TEST-ONLY original independent answer',
    sections: Object.fromEntries(item.sections.map((s, i) => [s.section_id, { minimal_evidence: i === 0, repair_packet: i === 0, note: '' }])),
    sets_reviewed: complete, saved_at: '2000-01-01T00:00:00.000Z' };
}
function legacyBackup() {
  return { schema_version: 'third_expert_blind_export.v1', study_id: manifest.study_id,
    manifest_hash: manifest.manifest_hash, parent_manifest_hash: manifest.parent_manifest_hash,
    translation_pack_hash: translations.translation_pack_hash, annotation_mode: 'blind_human_audit',
    annotation_protocol: 'binary_judgment_v1', review_protocol: 'targeted_third_blind_v1', expert_slot: 'expert_3',
    reviewer_id: 'TEST-ONLY-LEGACY3', anonymous_reviewer_id: 'TEST-ONLY-LEGACY3',
    order: [...manifest.expert_orders.expert_3], active_index: 0,
    annotations: { [first.presentation_id]: legacyRecord(first) }, exported_at: '2000-01-01T00:00:00.000Z' };
}
function legacyMethodBackup() {
  const backup = legacyBackup();
  return { ...backup, schema_version: 'third_expert_review_export.v2', annotation_mode: 'method_assisted_review',
    hint_pack_hash: hints.hint_pack_hash, parent_hint_pack_hash: hints.parent_hint_pack_hash,
    hints_visible: true, hints_displayed_case_ids: [...backup.order], legacy_blind_record_ids: [],
    annotations: Object.fromEntries(manifest.cases.map((item) => [item.presentation_id, {
      ...legacyRecord(item), annotation_mode: 'method_assisted_review', hint_pack_hash: hints.hint_pack_hash,
      hints_visible: true, hints_displayed: true, comments: 'TEST-ONLY old method review before injection markers',
    }])) };
}
async function noAutomaticAnswers(page) {
  assert.equal(await page.locator('[name="target_conflict"]:checked, [name="judgment_sufficient"]:checked').count(), 0);
  assert.equal(await page.locator('[data-minimal-evidence]:checked, [data-repair-packet]:checked').count(), 0);
  assert.equal(await page.locator('[name="confidence"]').inputValue(), '');
}
async function checkInjectionDisplay(page, item, visible) {
  const expected = markers.cases[item.presentation_id];
  const condition = page.locator('.sample-condition');
  assert.equal(await condition.count(), 1, `${item.presentation_id}: exactly one case condition badge`);
  assert.match(await condition.textContent(), expected.condition === 'post' ? /已注入/ : /未注入/);
  assert.equal(await condition.isVisible(), visible);
  assert.deepEqual((await page.locator('.paragraph-card:has(.injection-marker)').evaluateAll(
    (nodes) => nodes.map((node) => node.dataset.sectionId))).sort(), [...expected.modified_section_ids].sort(),
  `${item.presentation_id}: mark only the original modified paragraphs`);
  assert.equal(await page.locator('.injection-marker').count(), expected.modified_section_ids.length);
  assert.equal(await page.locator('.paragraph-number .injection-marker').count(), expected.modified_section_ids.length);
  assert.equal(await page.locator('.injection-marker:visible').count(), visible ? expected.modified_section_ids.length : 0);
  assert.equal(await page.locator('.algorithm-hints:visible').count(), visible ? item.sections.length : 0);
}
async function downloadJson(page) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#exportJsonBtn').click()]);
  return JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
}
async function downloadWorkbook(page) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#exportXlsxBtn').click()]);
  return page.evaluate((encoded) => {
    const wb = XLSX.read(Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)), { type: 'array' });
    return Object.fromEntries(wb.SheetNames.map((name) => [name, XLSX.utils.sheet_to_json(wb.Sheets[name], { defval: '' })]));
  }, fs.readFileSync(await download.path()).toString('base64'));
}

assert.ok(fs.existsSync(blindPath), 'Keep the unhinted HTML intact as a separate backup');
assert.ok(!fs.readFileSync(blindPath, 'utf8').includes('id="methodHintsData"'));
assert.ok(!fs.readFileSync(blindPath, 'utf8').includes('id="injectionMarkersData"'));
assert.deepEqual(embed('manifestData'), manifest);
assert.deepEqual(embed('translationData'), translations);
assert.equal(manifest.cases.length, 14);
assert.equal(manifest.cases.reduce((n, c) => n + c.sections.length, 0), 264);
assert.deepEqual(Object.keys(hints.cases).sort(), manifest.cases.map((c) => c.presentation_id).sort());
assert.equal(markers.schema_version, 'third_expert_injection_markers.v1');
assert.equal(markers.source_manifest_hash, manifest.manifest_hash);
assert.equal(markers.parent_manifest_hash, manifest.parent_manifest_hash);
assert.equal(markers.parent_marker_pack_hash, sourceMarkers.marker_pack_hash);
assert.match(markers.marker_pack_hash, /^sha256:[a-f0-9]{64}$/);
assert.deepEqual(Object.keys(markers.cases).sort(), manifest.cases.map((c) => c.presentation_id).sort());
for (const item of manifest.cases) {
  const marker = markers.cases[item.presentation_id];
  assert.deepEqual(marker, sourceMarkers.cases[item.presentation_id]);
  assert.deepEqual(Object.keys(marker).sort(), ['condition', 'modified_section_ids']);
  assert.ok(['pre', 'post'].includes(marker.condition));
  conditionCounts[marker.condition]++;
  assert.equal(new Set(marker.modified_section_ids).size, marker.modified_section_ids.length);
  for (const id of marker.modified_section_ids) assert.ok(item.sections.some((section) => section.section_id === id));
  if (marker.condition === 'pre') assert.deepEqual(marker.modified_section_ids, []);
  else assert.ok(marker.modified_section_ids.length > 0);
  markedParagraphs += marker.modified_section_ids.length;
  const subset = hints.cases[item.presentation_id];
  assert.ok(!Object.hasOwn(subset, 'condition'));
  assert.deepEqual(subset.sections, sourceHints.cases[item.presentation_id].sections);
  assert.equal(Object.keys(subset.sections).length, item.sections.length);
  for (const section of Object.values(subset.sections)) {
    assert.deepEqual(Object.keys(section.methods).sort(), ['lea', 'sa-mcgs']);
    for (const method of Object.values(section.methods)) assert.deepEqual(Object.keys(method.models).sort(), ['gemini-2.5-pro', 'gpt-4o']);
  }
}
assert.deepEqual(conditionCounts, { pre: 9, post: 5 });
assert.equal(markedParagraphs, 13);
for (const forbidden of ['source_physical_fingerprint', 'minimal_jaccard', 'repair_jaccard', 'target_disagreement', '"expert_1"', '"expert_2"', '"injection_identity":']) assert.ok(!html.includes(forbidden), `Private data leaked: ${forbidden}`);
assert.ok(!JSON.stringify({ manifest, translations, hints }).includes('"condition":'));

async function main() {
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'sa-mcgs-third-hints-qa-'));
  const browser = await chromium.launch({ headless: true, ...(process.env.ANNOTATION_CHROMIUM_PATH ? { executablePath: process.env.ANNOTATION_CHROMIUM_PATH } : {}) });
  try {
    const errors = [], remoteRequests = [];
    async function newPage(initial = null) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, offline: true, acceptDownloads: true });
      const page = await context.newPage();
      page.on('pageerror', (error) => errors.push(String(error)));
      page.on('request', (request) => { if (/^https?:/.test(request.url())) remoteRequests.push(request.url()); });
      page.on('dialog', (dialog) => dialog.accept());
      if (initial) await page.addInitScript(({ key, raw }) => localStorage.setItem(key, raw), { key: oldStorageKey, raw: JSON.stringify(initial) });
      await page.goto(pathToFileURL(htmlPath).href);
      await page.waitForFunction(() => !!window.ThirdExpertReview);
      return page;
    }
    const page = await newPage();
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().annotations), {});
    assert.equal(await page.locator('#progressText').textContent(), '0 / 14');
    assert.equal(await page.evaluate(() => ThirdExpertReview.getHintsVisible()), true);
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getHintsData()), hints);
    assert.equal(await page.locator('.algorithm-hints:visible').count(), first.sections.length);
    assert.equal(await page.locator('.model-hint').count(), first.sections.length * 4);
    await checkInjectionDisplay(page, first, true);
    await noAutomaticAnswers(page);
    await page.screenshot({ path: path.join(artifacts, 'desktop-hints.png') });
    await page.screenshot({ path: path.join(artifacts, 'desktop-fullpage.png'), fullPage: true });
    const initial = await page.evaluate(() => ThirdExpertReview.getSnapshot());
    assert.equal(initial.schema_version, 'third_expert_review_export.v2');
    assert.equal(initial.annotation_mode, 'method_assisted_review');
    assert.equal(initial.hint_pack_hash, hints.hint_pack_hash);
    assert.equal(initial.hints_visible, true);
    assert.ok(initial.hints_displayed_case_ids.includes(first.presentation_id));
    assert.equal(initial.injection_marker_pack_hash, markers.marker_pack_hash);
    assert.deepEqual(initial.injection_hints_displayed_case_ids, [first.presentation_id]);
    assert.deepEqual(initial.legacy_blind_record_ids, []);
    // Check every rendered score and selection across all 264 paragraphs.
    let visibleCells = 0;
    for (let index = 0; index < manifest.cases.length; index++) {
      const item = manifest.cases[index];
      await page.locator(`#caseList [data-index="${index}"]`).click();
      await checkInjectionDisplay(page, item, true);
      await noAutomaticAnswers(page);
      assert.equal(await page.locator('.model-hint').count(), item.sections.length * 4);
      for (const section of item.sections) {
        const card = page.locator(`.paragraph-card[data-section-id="${section.section_id}"]`);
        const content = await card.locator('.algorithm-hints').textContent();
        assert.match(content, /LEA/); assert.match(content, /SA-MCGS/); assert.match(content, /GPT-4o/); assert.match(content, /Gemini 2\.5 Pro/);
        const texts = await card.locator('.model-hint').allTextContents();
        const models = ['gpt-4o', 'gemini-2.5-pro'];
        for (const [methodIndex, method] of ['lea', 'sa-mcgs'].entries()) {
          for (const [modelIndex, model] of models.entries()) {
            const expected = sourceHints.cases[item.presentation_id].sections[section.section_id].methods[method].models[model];
            const text = texts[methodIndex * 2 + modelIndex];
            if (expected.status === 'available') {
              assert.ok(text.includes(expected.selected ? '已纳入结果子图' : '未纳入结果子图'));
              assert.ok(text.includes(Number(expected.score).toFixed(3)), `${item.presentation_id}/${section.section_id}/${method}/${model} score mismatch`);
              assert.ok(text.includes(`${expected.rank} / ${expected.total_nodes}`));
            } else {
              assert.match(text, /暂无可靠提示/);
            }
            visibleCells++;
          }
        }
      }
    }
    assert.equal(visibleCells, 1056);
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().annotations), {}, 'Viewing algorithm hints must not fabricate annotations');
    assert.equal(await page.locator('#progressText').textContent(), '0 / 14');
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().injection_hints_displayed_case_ids), manifest.expert_orders.expert_3);
    const postIndex = manifest.cases.findIndex((item) => markers.cases[item.presentation_id].condition === 'post');
    const postItem = manifest.cases[postIndex];
    await page.locator(`#caseList [data-index="${postIndex}"]`).click();
    await page.locator('.injection-marker').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(artifacts, 'desktop-injection-marker.png') });
    const beforeHide = await page.evaluate(() => ThirdExpertReview.getSnapshot());
    await page.locator('#toggleHintsBtn').click();
    await checkInjectionDisplay(page, postItem, false);
    await noAutomaticAnswers(page);
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().annotations), beforeHide.annotations);
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().injection_hints_displayed_case_ids), beforeHide.injection_hints_displayed_case_ids);
    await page.locator('#caseList [data-index="0"]').click();
    await checkInjectionDisplay(page, first, false);
    await page.locator('#toggleHintsBtn').click();
    await checkInjectionDisplay(page, first, true);

    // All 14 complete answers from the pre-marker v2 remain exact records;
    // their old algorithm exposure must not become injection-marker exposure.
    const oldV2 = legacyMethodBackup();
    const oldMethod = await newPage(oldV2);
    assert.equal(await oldMethod.locator('#progressText').textContent(), '14 / 14');
    let oldMethodSnapshot = await oldMethod.evaluate(() => ThirdExpertReview.getSnapshot());
    assert.deepEqual(oldMethodSnapshot.annotations, oldV2.annotations);
    assert.deepEqual(oldMethodSnapshot.hints_displayed_case_ids, oldV2.hints_displayed_case_ids);
    assert.deepEqual(oldMethodSnapshot.injection_hints_displayed_case_ids, [first.presentation_id]);
    await oldMethod.locator('#toggleHintsBtn').click();
    await oldMethod.locator('#caseList [data-index="1"]').click();
    await checkInjectionDisplay(oldMethod, manifest.cases[1], false);
    await oldMethod.locator('[name="comments"]').dispatchEvent('input');
    await oldMethod.locator('#saveCurrentBtn').click();
    assert.equal(await oldMethod.locator('#progressText').textContent(), '14 / 14');
    const oldMethodExport = await downloadJson(oldMethod);
    assert.deepEqual(oldMethodExport.annotations, oldV2.annotations);
    assert.deepEqual(oldMethodExport.injection_hints_displayed_case_ids, [first.presentation_id]);
    assert.equal(oldMethodExport.injection_marker_pack_hash, markers.marker_pack_hash);
    let oldMethodSheets = await downloadWorkbook(oldMethod);
    assert.equal(oldMethodSheets.版本信息[0].injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(oldMethodSheets.版本信息[0].已确认样本数, 14);
    for (const row of [...oldMethodSheets.样本整体标注, ...oldMethodSheets.逐段标注]) {
      assert.equal(row.annotation_mode, 'method_assisted_review');
      assert.equal(row.hint_pack_hash, hints.hint_pack_hash);
      assert.equal(row.injection_marker_pack_hash, '', 'Do not retrofit marker provenance onto historical answers');
      assert.equal(row.injection_hints_visible, '');
      assert.equal(row.injection_hints_displayed, '');
    }
    assert.deepEqual(await oldMethod.evaluate(() => ThirdExpertReview.getSnapshot().annotations), oldV2.annotations);
    await oldMethod.locator('#caseList [data-index="0"]').click();
    await oldMethod.locator('#toggleHintsBtn').click();
    assert.deepEqual(await oldMethod.evaluate(() => ThirdExpertReview.getSnapshot().annotations), oldV2.annotations);
    await oldMethod.locator('[name="comments"]').fill('TEST-ONLY first real edit after markers became available');
    oldMethodSnapshot = await oldMethod.evaluate(() => ThirdExpertReview.getSnapshot());
    const methodEdited = oldMethodSnapshot.annotations[first.presentation_id];
    assert.equal(methodEdited.injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(methodEdited.injection_hints_visible, true);
    assert.equal(methodEdited.injection_hints_displayed, true);
    assert.equal(methodEdited.sets_reviewed, false);
    assert.equal(methodEdited.target_conflict, oldV2.annotations[first.presentation_id].target_conflict);
    assert.deepEqual(methodEdited.sections, oldV2.annotations[first.presentation_id].sections);
    assert.equal(await oldMethod.locator('#progressText').textContent(), '13 / 14');
    for (const item of manifest.cases.slice(1)) assert.deepEqual(oldMethodSnapshot.annotations[item.presentation_id], oldV2.annotations[item.presentation_id]);
    oldMethodSheets = await downloadWorkbook(oldMethod);
    assert.equal(oldMethodSheets.样本整体标注.find((row) => row.样本编号 === first.presentation_id).injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(oldMethodSheets.样本整体标注.find((row) => row.样本编号 === manifest.cases[1].presentation_id).injection_marker_pack_hash, '');

    const oldV2Restore = await newPage();
    assert.equal(await oldV2Restore.evaluate((raw) => ThirdExpertReview.validateBackup(raw), oldV2), true);
    assert.equal(await oldV2Restore.evaluate((raw) => ThirdExpertReview.restoreBackup(raw), oldV2), true);
    assert.deepEqual(await oldV2Restore.evaluate(() => ThirdExpertReview.getSnapshot().annotations), oldV2.annotations);
    assert.equal(await oldV2Restore.locator('#progressText').textContent(), '14 / 14');
    assert.deepEqual(await oldV2Restore.evaluate(() => ThirdExpertReview.getSnapshot().injection_hints_displayed_case_ids), [first.presentation_id]);
    const oldHidden = await newPage({ ...oldV2, hints_visible: false });
    await checkInjectionDisplay(oldHidden, first, false);
    assert.deepEqual(await oldHidden.evaluate(() => ThirdExpertReview.getSnapshot().annotations), oldV2.annotations);
    assert.deepEqual(await oldHidden.evaluate(() => ThirdExpertReview.getSnapshot().injection_hints_displayed_case_ids), []);
    assert.equal(await oldHidden.locator('#progressText').textContent(), '14 / 14');

    // Legacy localStorage: old independent answers remain byte-for-byte record
    // copies even though the surrounding export records this page's provenance.
    const legacy = legacyBackup();
    const migrated = await newPage(legacy);
    assert.equal(await migrated.locator('#reviewerId').inputValue(), 'TEST-ONLY-LEGACY3');
    assert.equal(await migrated.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), true);
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations);
    let snapshot = await migrated.evaluate(() => ThirdExpertReview.getSnapshot());
    assert.equal(snapshot.annotation_mode, 'method_assisted_review');
    assert.deepEqual(snapshot.legacy_blind_record_ids, [first.presentation_id]);
    const stored = await migrated.evaluate(() => Object.entries(localStorage));
    assert.ok(stored.some(([key, value]) => key !== oldStorageKey && value === JSON.stringify(legacy)), 'Original blind state must be archived during migration');
    await migrated.locator('#toggleHintsBtn').click();
    await checkInjectionDisplay(migrated, first, false);
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations);
    await migrated.locator('#toggleHintsBtn').click();
    await checkInjectionDisplay(migrated, first, true);
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations);
    await migrated.locator('[name="comments"]').dispatchEvent('input');
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations, 'No-op input must not relabel existing independent work');
    await migrated.locator('#saveCurrentBtn').click();
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations, 'Reconfirming unchanged legacy answers must preserve their provenance');
    const beforeToggle = await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations);
    await migrated.locator('#toggleHintsBtn').click();
    await migrated.locator('#caseList [data-index="1"]').click();
    assert.deepEqual(await migrated.evaluate(() => ThirdExpertReview.getSnapshot().annotations), beforeToggle);
    // A new response made with hints hidden still comes from the assisted page,
    // but records that this case's hints have never been displayed in the UI.
    const second = manifest.cases[1];
    await migrated.locator('[name="target_conflict"][value="absent"]').check();
    await migrated.locator('[name="judgment_sufficient"][value="no"]').check();
    await migrated.locator('[name="confidence"]').selectOption('2');
    await migrated.locator('#saveCurrentBtn').click();
    let secondRecord = await migrated.evaluate((id) => ThirdExpertReview.getSnapshot().annotations[id], second.presentation_id);
    assert.equal(secondRecord.annotation_mode, 'method_assisted_review');
    assert.equal(secondRecord.hint_pack_hash, hints.hint_pack_hash);
    assert.equal(secondRecord.hints_visible, false);
    assert.equal(secondRecord.hints_displayed, false);
    assert.equal(secondRecord.injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(secondRecord.injection_hints_visible, false);
    assert.equal(secondRecord.injection_hints_displayed, false);
    assert.equal(secondRecord.sets_reviewed, true);
    await migrated.locator('#toggleHintsBtn').click();
    assert.deepEqual(await migrated.evaluate((id) => ThirdExpertReview.getSnapshot().annotations[id], second.presentation_id), secondRecord, 'Showing hints is not an answer edit');
    await migrated.locator('[name="comments"]').fill('TEST-ONLY changed with hints visible');
    secondRecord = await migrated.evaluate((id) => ThirdExpertReview.getSnapshot().annotations[id], second.presentation_id);
    assert.equal(secondRecord.hints_visible, true); assert.equal(secondRecord.hints_displayed, true); assert.equal(secondRecord.sets_reviewed, false);
    assert.equal(secondRecord.injection_hints_visible, true); assert.equal(secondRecord.injection_hints_displayed, true);
    await migrated.locator('#saveCurrentBtn').click();
    assert.deepEqual(await migrated.evaluate((id) => ThirdExpertReview.getSnapshot().annotations[id], first.presentation_id), legacy.annotations[first.presentation_id]);

    const [download] = await Promise.all([migrated.waitForEvent('download'), migrated.locator('#exportXlsxBtn').click()]);
    const xlsxBytes = fs.readFileSync(await download.path());
    const sheets = await migrated.evaluate((encoded) => {
      const wb = XLSX.read(Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0)), { type: 'array' });
      return Object.fromEntries(wb.SheetNames.map((name) => [name, XLSX.utils.sheet_to_json(wb.Sheets[name], { defval: '' })]));
    }, xlsxBytes.toString('base64'));
    assert.equal(sheets.样本整体标注.length, 14); assert.equal(sheets.逐段标注.length, 264); assert.equal(sheets.版本信息.length, 1);
    assert.equal(sheets.版本信息[0].annotation_mode, 'method_assisted_review');
    assert.equal(sheets.版本信息[0].injection_marker_pack_hash, markers.marker_pack_hash);
    assert.ok(sheets.版本信息[0].injection_hints_displayed_case_ids.split(';').includes(second.presentation_id));
    for (const row of [...sheets.样本整体标注, ...sheets.逐段标注]) {
      assert.equal(row.page_annotation_mode, 'method_assisted_review');
      assert.equal(row.schema_version, 'third_expert_review_export.v2');
      assert.equal(row.expert_slot, 'expert_3');
    }
    assert.equal(sheets.样本整体标注.find((r) => r.样本编号 === first.presentation_id).annotation_mode, 'blind_human_audit');
    assert.equal(sheets.样本整体标注.find((r) => r.样本编号 === second.presentation_id).annotation_mode, 'method_assisted_review');
    for (const row of [...sheets.样本整体标注, ...sheets.逐段标注].filter((r) => r.样本编号 === first.presentation_id)) {
      for (const field of markerFields) assert.equal(row[field], '', `Legacy v1 ${field} must remain unknown`);
    }
    for (const row of [...sheets.样本整体标注, ...sheets.逐段标注].filter((r) => r.样本编号 === second.presentation_id)) {
      assert.equal(row.injection_marker_pack_hash, markers.marker_pack_hash);
      assert.equal(row.injection_hints_visible, true);
      assert.equal(row.injection_hints_displayed, true);
    }
    const [jsonDownload] = await Promise.all([migrated.waitForEvent('download'), migrated.locator('#exportJsonBtn').click()]);
    const v2 = JSON.parse(fs.readFileSync(await jsonDownload.path(), 'utf8'));
    assert.equal(v2.schema_version, 'third_expert_review_export.v2');
    assert.equal(v2.injection_marker_pack_hash, markers.marker_pack_hash);
    assert.deepEqual(v2.injection_hints_displayed_case_ids, [first.presentation_id, second.presentation_id]);
    assert.deepEqual(v2.annotations[first.presentation_id], legacy.annotations[first.presentation_id]);
    assert.equal(await migrated.evaluate((raw) => ThirdExpertReview.validateBackup(raw), v2), true);
    const restored = await newPage();
    assert.equal(await restored.evaluate((raw) => ThirdExpertReview.restoreBackup(raw), v2), true);
    assert.deepEqual(await restored.evaluate(() => ThirdExpertReview.getSnapshot().annotations), v2.annotations);
    // Legacy JSON restore is accepted; current UI exposure is not erased.
    assert.equal(await restored.evaluate((raw) => ThirdExpertReview.restoreBackup(raw), legacy), true);
    assert.deepEqual(await restored.evaluate(() => ThirdExpertReview.getSnapshot().annotations), legacy.annotations);
    assert.ok((await restored.evaluate(() => ThirdExpertReview.getSnapshot())).hints_displayed_case_ids.includes(second.presentation_id));
    assert.ok((await restored.evaluate(() => ThirdExpertReview.getSnapshot())).injection_hints_displayed_case_ids.includes(second.presentation_id));
    await restored.locator('[name="comments"]').fill('TEST-ONLY first real edit of a legacy answer');
    const edited = await restored.evaluate(() => ThirdExpertReview.getSnapshot());
    assert.equal(edited.annotations[first.presentation_id].annotation_mode, 'method_assisted_review');
    assert.equal(edited.annotations[first.presentation_id].hint_pack_hash, hints.hint_pack_hash);
    assert.equal(edited.annotations[first.presentation_id].injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(edited.annotations[first.presentation_id].injection_hints_visible, true);
    assert.equal(edited.annotations[first.presentation_id].injection_hints_displayed, true);
    assert.equal(edited.annotations[first.presentation_id].sets_reviewed, false);
    assert.ok(!edited.legacy_blind_record_ids.includes(first.presentation_id));
    assert.equal(edited.annotations[first.presentation_id].target_conflict, legacy.annotations[first.presentation_id].target_conflict);
    const bad = clone(v2); bad.annotations[second.presentation_id].hints_visible = 'true';
    const beforeBad = stable(await restored.evaluate(() => ThirdExpertReview.getSnapshot()));
    const rejected = await restored.evaluate((raw) => { try { ThirdExpertReview.restoreBackup(raw); return ''; } catch (error) { return error.message; } }, bad);
    assert.ok(rejected); assert.deepEqual(stable(await restored.evaluate(() => ThirdExpertReview.getSnapshot())), beforeBad);
    // Invalid marker provenance must fail before touching answers, history or storage.
    const malformed = [];
    const wrongHash = clone(v2); wrongHash.injection_marker_pack_hash = `sha256:${'0'.repeat(64)}`; malformed.push(wrongHash);
    const invalidVisibility = clone(v2); invalidVisibility.annotations[second.presentation_id].injection_hints_visible = 'true'; malformed.push(invalidVisibility);
    const missingHistory = clone(v2); missingHistory.injection_hints_displayed_case_ids = []; malformed.push(missingHistory);
    const unknownHistory = clone(v2); unknownHistory.injection_hints_displayed_case_ids.push('TEST-UNKNOWN-ID'); malformed.push(unknownHistory);
    const incompleteRecord = clone(v2); delete incompleteRecord.annotations[second.presentation_id].injection_hints_displayed; malformed.push(incompleteRecord);
    const inconsistentVisibility = clone(v2); inconsistentVisibility.annotations[second.presentation_id].injection_hints_visible = false; malformed.push(inconsistentVisibility);
    for (const raw of malformed) {
      const storageBefore = await restored.evaluate(() => Object.entries(localStorage).sort());
      const error = await restored.evaluate((input) => { try { ThirdExpertReview.restoreBackup(input); return ''; } catch (caught) { return caught.message; } }, raw);
      assert.ok(error, 'Invalid injection metadata must be rejected');
      assert.deepEqual(stable(await restored.evaluate(() => ThirdExpertReview.getSnapshot())), beforeBad);
      assert.deepEqual(await restored.evaluate(() => Object.entries(localStorage).sort()), storageBefore);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(`#caseList [data-index="${postIndex}"]`).click();
    await page.locator('.injection-marker').first().scrollIntoViewIfNeeded();
    await checkInjectionDisplay(page, postItem, true);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(artifacts, 'mobile-hints.png') });
    assert.deepEqual(errors, []); assert.deepEqual(remoteRequests, []);
    console.log(JSON.stringify({ status: 'pass', cases: 14, sections: 264, hintCells: visibleCells,
      conditionCounts, markedParagraphs, sourceMarkersExact: true, sourceHintsExact: true, zeroRemoteRequests: true, noOtherRaterLeak: true,
      legacyStoredAnswersPreserved: true, legacyJsonRestorePreserved: true, togglePreservesConfirmation: true,
      oldV2StoredAndJsonAnswersPreserved: true, oldAlgorithmExposureNotInferredAsInjectionExposure: true,
      unifiedHintToggle: true, noAutomaticAnswers: true, editedAnswerProvenanceStamped: true,
      mixedModeXlsxCorrect: true, invalidMarkerMetadataRejectedAtomically: true, mobileOverflow: false, screenshots: artifacts }, null, 2));
  } finally { await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
