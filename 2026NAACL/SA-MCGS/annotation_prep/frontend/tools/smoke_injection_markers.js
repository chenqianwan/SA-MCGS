#!/usr/bin/env node
'use strict';

// Offline, disposable Chromium contexts only. Every answer below is synthetic;
// the user's browser profile and real expert labels are never read or changed.
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
function embedded(id) {
  const match = html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`));
  assert.ok(match, `Missing embedded ${id}`);
  return JSON.parse(match[1]);
}
const manifest = embedded('manifestData');
const translations = embedded('translationData');
const hints = embedded('methodHintsData');
const markers = embedded('injectionMarkersData');
const PROTOCOL = 'binary_judgment_v1';
const sorted = (values) => [...values].sort();

async function download(page, button) {
  const [item] = await Promise.all([page.waitForEvent('download'), page.locator(`#${button}`).click()]);
  return fs.readFileSync(await item.path());
}

async function jsonBackup(page) {
  const payload = JSON.parse((await download(page, 'exportJsonBtn')).toString('utf8'));
  assert.equal(payload.annotation_mode, 'method_assisted_review');
  assert.equal(payload.annotation_protocol, PROTOCOL);
  assert.equal(payload.hint_pack_hash, hints.hint_pack_hash);
  assert.equal(payload.injection_marker_pack_hash, markers.marker_pack_hash);
  return payload;
}

async function chooseCase(page, index) {
  await page.evaluate((value) => navigateTo(value), index);
  await page.locator('#saveCurrentBtn').waitFor();
}

async function badgeSections(page) {
  return sorted(await page.locator('.paragraph-card:has(.injection-marker)').evaluateAll(
    (nodes) => nodes.map((node) => node.dataset.sectionId),
  ));
}

async function noAutomaticAnswers(page) {
  assert.equal(await page.locator('input[name="target_conflict"]:checked').count(), 0);
  assert.equal(await page.locator('input[name="judgment_sufficient"]:checked').count(), 0);
  assert.equal(await page.locator('[data-minimal-evidence]:checked, [data-repair-packet]:checked').count(), 0);
  assert.equal(await page.locator('[data-section-role]:checked:not([value=""])').count(), 0);
  assert.equal(await page.locator('select[name="confidence"]').inputValue(), '');
}

function oldRecord(item) {
  return {
    annotation_protocol: PROTOCOL,
    reviewer_id: 'TEST-OLD-REVIEWER', expert_slot: 'expert_1',
    target_conflict: 'absent', judgment_sufficient: 'yes',
    confidence: '4', sets_reviewed: true,
    comments: 'SYNTHETIC RECORD FROM BEFORE INJECTION MARKERS',
    saved_at: '2000-01-01T00:00:00.000Z',
    hint_pack_hash: hints.hint_pack_hash,
    sections: Object.fromEntries(item.sections.map((section) => [section.section_id, {
      role: '', role_label: '', minimal_evidence: false,
      repair_packet: false, note: `UNCHANGED-${section.section_id}`,
    }])),
    extra_legacy_value: 'must not be rewritten by rendering',
  };
}

async function main() {
  assert.equal(markers.schema_version, 'assisted_injection_markers.v1');
  assert.equal(markers.source_manifest_hash, manifest.manifest_hash);
  assert.match(markers.marker_pack_hash, /^sha256:[0-9a-f]{64}$/);
  assert.equal(manifest.cases.length, 42);
  assert.deepEqual(sorted(Object.keys(markers.cases)), sorted(manifest.cases.map((item) => item.presentation_id)));
  const conditionCounts = { pre: 0, post: 0 };
  let markedParagraphs = 0;
  for (const item of manifest.cases) {
    const marker = markers.cases[item.presentation_id];
    assert.ok(['pre', 'post'].includes(marker.condition));
    conditionCounts[marker.condition] += 1;
    const sectionIds = new Set(item.sections.map((section) => section.section_id));
    assert.equal(new Set(marker.modified_section_ids).size, marker.modified_section_ids.length);
    for (const id of marker.modified_section_ids) assert.ok(sectionIds.has(id), `${item.presentation_id}: unknown section ${id}`);
    if (marker.condition === 'pre') assert.deepEqual(marker.modified_section_ids, []);
    else assert.ok(marker.modified_section_ids.length, `${item.presentation_id}: post must expose a changed paragraph`);
    markedParagraphs += marker.modified_section_ids.length;
  }
  assert.deepEqual(conditionCounts, { pre: 18, post: 24 });

  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'sa-mcgs-injection-marker-qa-'));
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.ANNOTATION_CHROMIUM_PATH ? { executablePath: process.env.ANNOTATION_CHROMIUM_PATH } : {}),
  });
  const errors = [];
  const remoteRequests = [];
  const attachChecks = (page) => {
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('request', (request) => { if (/^https?:/i.test(request.url())) remoteRequests.push(request.url()); });
    page.on('dialog', (dialog) => dialog.accept());
  };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, offline: true });
    const page = await context.newPage();
    attachChecks(page);
    await page.goto(pathToFileURL(htmlPath).href);
    await page.locator('input[name="judgment_sufficient"]').first().waitFor();
    const actualStoreKey = await page.evaluate(() => storeKey());
    const order = manifest.expert_orders.expert_1;
    for (const [index, id] of order.entries()) {
      await chooseCase(page, index);
      assert.equal(await page.evaluate(() => currentCase().presentation_id), id);
      const expected = sorted(markers.cases[id].modified_section_ids);
      assert.deepEqual(await badgeSections(page), expected, `Incorrect marker locations for ${id}`);
      assert.equal(await page.locator('.injection-marker').count(), expected.length, 'Exactly one badge per changed paragraph');
      assert.equal(await page.locator('.paragraph-number .injection-marker').count(), expected.length, 'Badges belong next to paragraph headings');
      for (const text of await page.locator('.injection-marker').allTextContents()) assert.match(text, /注入/);
      await noAutomaticAnswers(page);
      const sections = await page.locator('.paragraph-card').count();
      assert.equal(await page.locator('.model-hint').count(), sections * 4, 'Existing method/model hints must remain intact');
      assert.deepEqual(await page.locator('input[name="target_conflict"]').evaluateAll((nodes) => nodes.map((node) => node.value)), ['present', 'absent']);
      assert.deepEqual(await page.locator('input[name="judgment_sufficient"]').evaluateAll((nodes) => nodes.map((node) => node.value)), ['yes', 'no']);
    }
    assert.deepEqual(await page.evaluate(() => state.annotations.expert_1 || {}), {}, 'Visiting all examples must not create answers');

    const postIndex = order.findIndex((id) => markers.cases[id].condition === 'post');
    await chooseCase(page, postIndex);
    const expected = sorted(markers.cases[order[postIndex]].modified_section_ids);
    await page.locator('#toggleHintsBtn').click();
    assert.equal(await page.locator('.algorithm-hints:visible').count(), 0);
    assert.deepEqual(await badgeSections(page), expected, 'Injection badges are independent of algorithm hint visibility');
    assert.equal(await page.locator('.injection-marker:visible').count(), expected.length);
    await noAutomaticAnswers(page);
    await page.locator('#toggleHintsBtn').click();
    assert.ok(await page.locator('.algorithm-hints:visible').count());
    assert.deepEqual(await badgeSections(page), expected);
    const selectedCard = page.locator('.paragraph-card:has(.injection-marker)').first();
    await selectedCard.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(artifacts, 'injection-marker-desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.injection-marker').first().scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page must not overflow horizontally');
    await page.screenshot({ path: path.join(artifacts, 'injection-marker-mobile.png') });
    await page.setViewportSize({ width: 1440, height: 1100 });

    const emptyExport = await jsonBackup(page);
    assert.deepEqual(emptyExport.annotations, {}, 'Export must not invent injection-grounded judgments');
    // New explicit edits are tagged with the marker pack that was visible.
    await page.locator('#reviewerId').fill('TEST-INJECTION-REVIEWER');
    await page.locator('input[name="target_conflict"][value="present"]').check();
    await page.waitForFunction((hash) => annotationFor(currentCase().presentation_id).injection_marker_pack_hash === hash, markers.marker_pack_hash);
    const edited = await jsonBackup(page);
    assert.equal(edited.annotations[order[postIndex]].injection_marker_pack_hash, markers.marker_pack_hash);
    assert.notEqual(edited.annotations[order[postIndex]].sets_reviewed, true);
    const XLSX = require(path.join(frontend, 'vendor', 'xlsx.full.min.js'));
    const workbook = XLSX.read(await download(page, 'exportXlsxBtn'), { type: 'buffer' });
    const metadata = XLSX.utils.sheet_to_json(workbook.Sheets['版本信息'])[0];
    assert.equal(metadata.injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(metadata.annotation_mode, 'method_assisted_review');

    // A previously saved binary record has no marker exposure metadata. Merely
    // visiting, switching hints, navigating and exporting cannot add that field.
    const legacyContext = await browser.newContext({ viewport: { width: 1440, height: 1100 }, offline: true });
    const legacy = await legacyContext.newPage();
    attachChecks(legacy);
    const oldId = order[postIndex];
    const item = manifest.cases.find((entry) => entry.presentation_id === oldId);
    const previous = oldRecord(item);
    const oldAnnotations = { [oldId]: previous };
    const raw = JSON.stringify({
      schema_version: 'assisted_standalone_annotation.state.v1', annotation_mode: 'method_assisted_review',
      annotation_protocol: PROTOCOL,
      study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      translation_pack_hash: translations.translation_pack_hash, hint_pack_hash: hints.hint_pack_hash,
      hint_pack_history: [hints.hint_pack_hash], hints_visible: true,
      progress_origin: 'SYNTHETIC-PRE-MARKER', orders: manifest.expert_orders,
      active_expert: 'expert_1', active_indices: { expert_1: postIndex },
      annotations: { expert_1: oldAnnotations }, reviewer_ids: { expert_1: 'TEST-OLD-REVIEWER' },
    });
    await legacy.addInitScript(({ key, value }) => localStorage.setItem(key, value), { key: actualStoreKey, value: raw });
    await legacy.goto(pathToFileURL(htmlPath).href);
    await legacy.locator('input[name="judgment_sufficient"]').first().waitFor();
    assert.deepEqual(await legacy.evaluate(() => state.annotations.expert_1), oldAnnotations);
    await legacy.locator('#toggleHintsBtn').click();
    await legacy.locator('#toggleHintsBtn').click();
    await chooseCase(legacy, (postIndex + 1) % order.length);
    await chooseCase(legacy, postIndex);
    const oldExport = await jsonBackup(legacy);
    assert.deepEqual(oldExport.annotations, oldAnnotations, 'Old records must retain their original marker-unexposed provenance');
    await download(legacy, 'exportCsvBtn');
    await download(legacy, 'exportXlsxBtn');
    assert.deepEqual(await legacy.evaluate(() => state.annotations.expert_1), oldAnnotations);
    await legacy.locator('select[name="confidence"]').selectOption('5');
    await legacy.waitForFunction((hash) => annotationFor(currentCase().presentation_id).injection_marker_pack_hash === hash, markers.marker_pack_hash);
    const revised = await jsonBackup(legacy);
    assert.equal(revised.annotations[oldId].confidence, '5');
    assert.equal(revised.annotations[oldId].injection_marker_pack_hash, markers.marker_pack_hash);
    assert.equal(revised.annotations[oldId].extra_legacy_value, previous.extra_legacy_value);
    assert.equal(revised.annotations[oldId].sets_reviewed, false);

    assert.deepEqual(errors, [], 'Browser console/page errors');
    assert.deepEqual(remoteRequests, [], 'Standalone page must not request remote resources');
    console.log(JSON.stringify({ ok: true, cases_checked: order.length, condition_counts: conditionCounts,
      marked_paragraphs: markedParagraphs, marker_pack_hash: markers.marker_pack_hash,
      no_automatic_answers: true, old_records_preserved: true, export_metadata_verified: true,
      offline: true, artifacts }, null, 2));
    await legacyContext.close();
    await context.close();
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
