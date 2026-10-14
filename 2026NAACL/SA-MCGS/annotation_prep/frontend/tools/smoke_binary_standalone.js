#!/usr/bin/env node
'use strict';

// Disposable, offline Chromium contexts only. No real expert/browser data is
// read or changed; all filled answers below are deliberately synthetic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

const frontend = path.resolve(__dirname, '..');
const htmlPath = process.argv[2] ? path.resolve(process.argv[2])
  : path.join(frontend, '..', 'dist', 'sa_mcgs_blind_annotation.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const embedded = (id) => JSON.parse(html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`))[1]);
const manifest = embedded('manifestData');
const translations = embedded('translationData');
const hints = embedded('methodHintsData');
const PROTOCOL = 'binary_judgment_v1';
const clone = (value) => JSON.parse(JSON.stringify(value));

async function download(page, button) {
  const [item] = await Promise.all([page.waitForEvent('download'), page.locator(`#${button}`).click()]);
  return { filename: item.suggestedFilename(), bytes: fs.readFileSync(await item.path()) };
}

async function jsonBackup(page) {
  const item = await download(page, 'exportJsonBtn');
  const payload = JSON.parse(item.bytes.toString('utf8'));
  assert.equal(payload.annotation_mode, 'method_assisted_review');
  assert.equal(payload.annotation_protocol, PROTOCOL);
  assert.equal(payload.hint_pack_hash, hints.hint_pack_hash);
  return payload;
}

async function currentAnnotation(page) {
  return page.evaluate(() => JSON.parse(JSON.stringify(annotationFor(currentCase().presentation_id))));
}

async function chooseCase(page, index) {
  await page.evaluate((value) => navigateTo(value), index);
  await page.locator('#saveCurrentBtn').waitFor();
}

async function chooseJudgment(page, target, sufficient, confidence = '4') {
  await page.locator(`input[name="target_conflict"][value="${target}"]`).check();
  await page.locator(`input[name="judgment_sufficient"][value="${sufficient}"]`).check();
  await page.locator('select[name="confidence"]').selectOption(confidence);
  await page.waitForFunction(({ target, sufficient, confidence }) => {
    const value = annotationFor(currentCase().presentation_id);
    return value.target_conflict === target && value.judgment_sufficient === sufficient
      && String(value.confidence) === confidence;
  }, { target, sufficient, confidence });
}

function legacyAnnotation(item, target, sufficient, confidence) {
  return {
    reviewer_id: 'TEST-LEGACY-REVIEWER', expert_slot: 'expert_1',
    target_conflict: target, evidence_sufficient: sufficient,
    need_more_context: target === 'insufficient' ? 'yes' : 'no', confidence,
    comments: 'UNCHANGED-LEGACY-TEST-COMMENT', saved_at: '2000-01-01T00:00:00.000Z',
    sections: Object.fromEntries(item.sections.map((section, index) => [section.section_id, {
      role: index === 0 ? 'supporting_context' : 'ordinary_context',
      role_label: index === 0 ? '相关证据或解释' : '一般上下文',
      minimal_evidence: false, repair_packet: false,
      note: `UNCHANGED-LEGACY-${section.section_id}`,
    }])),
    extra_legacy_field: 'must-be-preserved',
  };
}

async function main() {
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'sa-mcgs-binary-qa-'));
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.ANNOTATION_CHROMIUM_PATH ? { executablePath: process.env.ANNOTATION_CHROMIUM_PATH } : {}),
  });
  const errors = [];
  const networkRequests = [];
  const attachChecks = (page) => {
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('request', (request) => { if (/^https?:/i.test(request.url())) networkRequests.push(request.url()); });
    page.on('dialog', (dialog) => dialog.accept());
  };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, offline: true });
    const page = await context.newPage();
    attachChecks(page);
    await page.goto(pathToFileURL(htmlPath).href);
    await page.locator('input[name="judgment_sufficient"]').first().waitFor();
    assert.equal(await page.evaluate(() => ANNOTATION_PROTOCOL), PROTOCOL);
    assert.ok((await page.evaluate(() => storeKey())).endsWith(`:${PROTOCOL}`));
    assert.deepEqual(await page.locator('input[name="target_conflict"]').evaluateAll((nodes) => nodes.map((node) => node.value)), ['present', 'absent']);
    assert.deepEqual(await page.locator('input[name="judgment_sufficient"]').evaluateAll((nodes) => nodes.map((node) => node.value)), ['yes', 'no']);
    assert.equal(await page.locator('input[name="evidence_sufficient"], input[name="need_more_context"]').count(), 0);
    assert.deepEqual(await page.locator('select[name="confidence"] option').evaluateAll((nodes) => nodes.map((node) => node.value).filter(Boolean)), ['1', '2', '3', '4', '5']);
    const sections = await page.locator('.paragraph-card').count();
    assert.equal(await page.locator('[data-minimal-evidence]').count(), sections);
    assert.equal(await page.locator('[data-repair-packet]').count(), sections);
    assert.equal(await page.locator('details.section-extras').count(), sections);
    assert.equal(await page.locator('[data-section-role]:visible, [data-section-note]:visible').count(), 0);
    assert.equal(await page.locator('[data-section-role]:checked:not([value=""])').count(), 0);
    assert.match(await page.locator('#saveCurrentBtn').textContent(), /确认.*保存/);
    assert.match(await page.locator('#nextCaseBtn').textContent(), /确认/);
    assert.equal(await page.locator('.model-hint').count(), sections * 4, 'Existing algorithm hints must remain available');
    await page.locator('.paragraph-form').first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(artifacts, 'binary-paragraph.png') });
    await page.locator('#reviewerId').fill('TEST-BINARY-REVIEWER');
    await page.waitForFunction(() => state.reviewerIds.expert_1 === 'TEST-BINARY-REVIEWER');

    // A fully supported negative requires no artificial conflict endpoint and no
    // deprecated paragraph-role selection, but still needs explicit confirmation.
    await chooseJudgment(page, 'absent', 'yes');
    let value = await currentAnnotation(page);
    const negativeId = await page.evaluate(() => currentCase().presentation_id);
    assert.equal(value.annotation_protocol, PROTOCOL);
    assert.notEqual(value.sets_reviewed, true);
    assert.equal(await page.evaluate(() => isComplete(currentCase().presentation_id)), false);
    const beforeDraftExport = await currentAnnotation(page);
    const draft = await jsonBackup(page);
    assert.deepEqual(await currentAnnotation(page), beforeDraftExport, 'Export must not silently confirm or modify a draft');
    assert.notEqual(draft.annotations[negativeId].sets_reviewed, true);
    await page.locator('#saveCurrentBtn').click();
    value = await currentAnnotation(page);
    assert.equal(value.sets_reviewed, true);
    assert.equal(await page.evaluate(() => isComplete(currentCase().presentation_id)), true);
    assert.equal(await page.evaluate(() => binaryScoringEligibility(annotationFor(currentCase().presentation_id))), 'negative');
    assert.equal(await page.locator('[data-section-role]:checked:not([value=""])').count(), 0, 'Roles must not be required for new annotations');
    await page.locator('select[name="confidence"]').selectOption('5');
    assert.equal((await currentAnnotation(page)).sets_reviewed, false, 'Editing a confirmed answer must invalidate confirmation');
    await page.locator('#saveCurrentBtn').click();

    // A supported positive must have a non-empty minimal evidence set contained
    // in the repair packet; optional role labels are still not mandatory.
    await chooseCase(page, 1);
    await chooseJudgment(page, 'present', 'yes');
    const positiveId = await page.evaluate(() => currentCase().presentation_id);
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate(() => isComplete(currentCase().presentation_id)), false, 'An empty positive minimal set is incomplete');
    assert.equal(await page.evaluate(() => validateCurrentCase().valid), false);
    await page.locator('[data-minimal-evidence]').first().check();
    assert.equal(await page.locator('[data-repair-packet]').first().isChecked(), true, 'Selecting minimal evidence must also include it in repair material');
    await page.locator('[data-repair-packet]').first().click();
    assert.equal(await page.locator('[data-repair-packet]').first().isChecked(), true, 'Cannot remove repair material while it is still minimal evidence');
    await page.locator('[data-repair-packet]').first().check();
    await page.evaluate(() => {
      const item = currentCase();
      annotationFor(item.presentation_id).sections[item.sections[0].section_id].repair_packet = false;
      renderAll();
    });
    assert.equal(await page.evaluate(() => validateCurrentCase().valid), false, 'Minimal evidence must be a subset of repair material');
    await page.locator('[data-repair-packet]').first().check();
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate(() => isComplete(currentCase().presentation_id)), true);
    assert.equal(await page.evaluate(() => binaryScoringEligibility(annotationFor(currentCase().presentation_id))), 'positive');
    assert.equal(await page.locator('[data-section-role]:checked:not([value=""])').count(), 0);
    const positiveRecord = await currentAnnotation(page);
    assert.equal(positiveRecord.sections[Object.keys(positiveRecord.sections)[0]].minimal_evidence, true);
    assert.equal(positiveRecord.sections[Object.keys(positiveRecord.sections)[0]].repair_packet, true);

    // "Not sufficient" is a complete reviewer response, not an inferred gold
    // label. It is explicitly excluded from positive/negative scoring.
    await chooseCase(page, 2);
    await chooseJudgment(page, 'present', 'no', '3');
    const insufficientId = await page.evaluate(() => currentCase().presentation_id);
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate(() => isComplete(currentCase().presentation_id)), true);
    assert.equal(await page.evaluate(() => binaryScoringEligibility(annotationFor(currentCase().presentation_id))), 'insufficient');
    const rows = await page.evaluate(() => buildExportRows().caseRows);
    const rowFor = (id) => rows.find((row) => row['样本编号'] === id);
    assert.equal(rowFor(negativeId).scoring_eligibility, 'negative');
    assert.equal(rowFor(positiveId).scoring_eligibility, 'positive');
    assert.equal(rowFor(insufficientId).scoring_eligibility, 'insufficient');
    assert.equal(rowFor(negativeId)['判断充分性代码'], 'yes');
    assert.equal(rowFor(insufficientId)['判断充分性代码'], 'no');
    assert.ok(Object.hasOwn(rowFor(insufficientId), '证据选择已确认'));
    const completedBackup = await jsonBackup(page);
    for (const id of [negativeId, positiveId, insufficientId]) {
      assert.equal(completedBackup.annotations[id].annotation_protocol, PROTOCOL);
      assert.equal(completedBackup.annotations[id].sets_reviewed, true);
    }
    const csv = await download(page, 'exportCsvBtn');
    assert.match(csv.bytes.toString('utf8'), /scoring_eligibility/);
    assert.match(csv.bytes.toString('utf8'), /insufficient/);
    assert.match(csv.bytes.toString('utf8'), /判断充分性代码/);
    const xlsx = await download(page, 'exportXlsxBtn');
    const XLSX = require(path.join(frontend, 'vendor', 'xlsx.full.min.js'));
    const workbook = XLSX.read(xlsx.bytes, { type: 'buffer' });
    const xlsxRows = XLSX.utils.sheet_to_json(workbook.Sheets['样本整体标注']);
    assert.equal(xlsxRows.find((row) => row['样本编号'] === insufficientId).scoring_eligibility, 'insufficient');
    const metadata = XLSX.utils.sheet_to_json(workbook.Sheets['版本信息'])[0];
    assert.equal(metadata.annotation_protocol, PROTOCOL);
    await page.locator('.overall-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(artifacts, 'binary-overall.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page overflows horizontally');
    await page.screenshot({ path: path.join(artifacts, 'binary-mobile.png') });

    // Preserve legacy records byte-for-byte until an actual edit. Merely opening,
    // navigating, rendering, or exporting must not reinterpret partial/NA labels.
    const legacyContext = await browser.newContext({ viewport: { width: 1440, height: 1100 }, offline: true });
    const legacy = await legacyContext.newPage();
    attachChecks(legacy);
    const order = manifest.expert_orders.expert_1;
    const byId = new Map(manifest.cases.map((item) => [item.presentation_id, item]));
    const legacyAnnotations = {
      [order[0]]: legacyAnnotation(byId.get(order[0]), 'absent', 'not_applicable', '4'),
      [order[1]]: legacyAnnotation(byId.get(order[1]), 'present', 'partial', '3'),
      [order[2]]: legacyAnnotation(byId.get(order[2]), 'insufficient', 'partial', '2'),
    };
    const legacyKey = `sa_mcgs_assisted_expert_audit_v1:${manifest.study_id}:${manifest.manifest_hash}:${hints.hint_pack_hash}`;
    const legacyRaw = JSON.stringify({
      schema_version: 'assisted_standalone_annotation.state.v1', annotation_mode: 'method_assisted_review',
      study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      translation_pack_hash: translations.translation_pack_hash, hint_pack_hash: hints.hint_pack_hash,
      hint_pack_history: [hints.hint_pack_hash], hints_visible: true,
      progress_origin: 'TEST-OLD-PROTOCOL', orders: manifest.expert_orders,
      active_expert: 'expert_1', active_indices: { expert_1: 0 },
      annotations: { expert_1: legacyAnnotations }, reviewer_ids: { expert_1: 'TEST-LEGACY-REVIEWER' },
    });
    await legacy.addInitScript(({ key, raw }) => localStorage.setItem(key, raw), { key: legacyKey, raw: legacyRaw });
    await legacy.goto(pathToFileURL(htmlPath).href);
    await legacy.locator('input[name="judgment_sufficient"]').first().waitFor();
    assert.notEqual(await legacy.evaluate(() => storeKey()), legacyKey);
    assert.ok((await legacy.evaluate(() => storeKey())).endsWith(`:${PROTOCOL}`));
    assert.deepEqual(await legacy.evaluate(() => state.annotations.expert_1), legacyAnnotations);
    for (const index of [0, 1, 2]) {
      await chooseCase(legacy, index);
      assert.equal(await legacy.locator('input[name="judgment_sufficient"]:checked').count(), 0, 'Old partial/NA must never become a selected binary judgment');
      if (index === 2) assert.equal(await legacy.locator('input[name="target_conflict"]:checked').count(), 0, 'Old target=insufficient must not become present or absent');
      assert.equal(await legacy.evaluate(() => isComplete(currentCase().presentation_id)), false);
      assert.equal(await legacy.evaluate(() => binaryScoringEligibility(annotationFor(currentCase().presentation_id))), 'legacy_pending_review');
      assert.deepEqual(await legacy.evaluate(() => state.annotations.expert_1), legacyAnnotations);
    }
    const legacyExport = await jsonBackup(legacy);
    assert.deepEqual(legacyExport.annotations, legacyAnnotations, 'JSON export must preserve all legacy fields and values');
    await download(legacy, 'exportCsvBtn');
    await download(legacy, 'exportXlsxBtn');
    assert.deepEqual(await legacy.evaluate(() => state.annotations.expert_1), legacyAnnotations, 'Tabular export must not mutate legacy records');
    assert.equal(await legacy.evaluate((key) => localStorage.getItem(key), legacyKey), legacyRaw);
    await chooseCase(legacy, 0);
    await legacy.locator('input[name="judgment_sufficient"][value="yes"]').check();
    const editedLegacy = await currentAnnotation(legacy);
    assert.equal(editedLegacy.annotation_protocol, PROTOCOL);
    assert.deepEqual(editedLegacy.legacy_annotation, legacyAnnotations[order[0]], 'The original record must be preserved exactly on first edit');
    assert.equal(editedLegacy.evidence_sufficient, 'not_applicable');
    assert.equal(editedLegacy.need_more_context, 'no');
    assert.equal(editedLegacy.sets_reviewed, false);
    await legacy.locator('#saveCurrentBtn').click();
    assert.equal(await legacy.evaluate(() => isComplete(currentCase().presentation_id)), true);
    assert.equal(await legacy.evaluate(() => binaryScoringEligibility(annotationFor(currentCase().presentation_id))), 'negative');
    await legacy.locator('select[name="confidence"]').selectOption('5');
    const editedAgain = await currentAnnotation(legacy);
    assert.deepEqual(editedAgain.legacy_annotation, legacyAnnotations[order[0]], 'Subsequent edits must not overwrite the first legacy snapshot');
    assert.equal(editedAgain.sets_reviewed, false);
    assert.equal(await legacy.evaluate((key) => localStorage.getItem(key), legacyKey), legacyRaw);
    await legacy.locator('.overall-panel').scrollIntoViewIfNeeded();
    await legacy.screenshot({ path: path.join(artifacts, 'legacy-binary-review.png') });

    // Restore the new protocol in a fresh disposable context. Labels and explicit
    // confirmation survive, while an unknown protocol cannot overwrite them.
    const restoreContext = await browser.newContext({ offline: true });
    const restore = await restoreContext.newPage();
    attachChecks(restore);
    await restore.goto(pathToFileURL(htmlPath).href);
    await restore.locator('input[name="judgment_sufficient"]').first().waitFor();
    await restore.evaluate(async (raw) => restoreBackup(raw), completedBackup);
    assert.deepEqual(await restore.evaluate(() => state.annotations.expert_1), completedBackup.annotations);
    for (const [id, eligibility] of [[negativeId, 'negative'], [positiveId, 'positive'], [insufficientId, 'insufficient']]) {
      assert.equal(await restore.evaluate((id) => isComplete(id), id), true);
      assert.equal(await restore.evaluate((id) => binaryScoringEligibility(annotationFor(id)), id), eligibility);
    }
    const beforeUnknownProtocol = await restore.evaluate(() => JSON.stringify(state));
    const unknownError = await restore.evaluate(async (raw) => {
      try { await restoreBackup(raw); return ''; } catch (error) { return error.message; }
    }, { ...completedBackup, annotation_protocol: 'unknown_protocol_test' });
    assert.match(unknownError, /协议|版本|protocol/i);
    assert.equal(await restore.evaluate(() => JSON.stringify(state)), beforeUnknownProtocol);

    assert.deepEqual(errors, []);
    assert.deepEqual(networkRequests, [], 'Offline QA attempted a remote request');
    console.log(JSON.stringify({
      status: 'pass', offline: true, protocol: PROTOCOL,
      binaryQuestions: true, roleOptional: true, explicitSetConfirmation: true,
      positiveMinimalSubset: true, negativeWithoutFakeEndpoints: true,
      insufficientCompleteButExcluded: true, jsonCsvXlsx: true,
      legacyUntouchedUntilEdited: true, exactLegacySnapshot: true,
      isolatedProtocolStorage: true, newBackupRoundTrip: true,
      mobileOverflow: false, artifacts,
    }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
