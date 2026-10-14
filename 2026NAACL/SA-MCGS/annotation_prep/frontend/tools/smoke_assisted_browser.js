#!/usr/bin/env node
'use strict';

// Isolated, offline browser QA; never uses a real user's browser profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const frontend = path.resolve(__dirname, '..');
const htmlPath = path.join(frontend, '..', 'dist', 'sa_mcgs_blind_annotation.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const embedded = (id) => JSON.parse(html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`))[1]);
const manifest = embedded('manifestData');
const translations = embedded('translationData');
const hints = embedded('methodHintsData');
const previousHash = hints.previous_hint_pack_hashes?.[0];
assert.ok(previousHash, 'The updated hint pack must list its compatible predecessor');

function assertHintHistory(history) {
  assert.ok(Array.isArray(history));
  assert.ok(history.includes(previousHash), 'Export must retain the old hint hash');
  assert.ok(history.includes(hints.hint_pack_hash), 'Export must retain the current hint hash');
  assert.equal(new Set(history).size, history.length);
}

function syntheticAnnotations(expertId) {
  return Object.fromEntries(manifest.cases.map((item) => [item.presentation_id, {
    reviewer_id: `TEST-ONLY-${expertId}`, expert_slot: expertId,
    target_conflict: 'present', evidence_sufficient: 'yes', need_more_context: 'no', confidence: '4',
    comments: `synthetic-${expertId}`, saved_at: '2000-01-01T00:00:00.000Z',
    sections: Object.fromEntries(item.sections.map((section, index) => [section.section_id, {
      role: index === 0 ? 'conflict_evidence' : 'ordinary_context',
      minimal_evidence: index === 0, repair_packet: index === 0,
      note: `synthetic-${expertId}-${item.presentation_id}-${section.section_id}`,
    }])),
  }]));
}

function labelsOnly(annotations) {
  return Object.fromEntries(Object.entries(annotations).map(([id, value]) => [id, {
    target_conflict: value.target_conflict, evidence_sufficient: value.evidence_sufficient,
    need_more_context: value.need_more_context, confidence: value.confidence, comments: value.comments,
    sections: Object.fromEntries(Object.entries(value.sections || {}).map(([sectionId, section]) => [sectionId, {
      role: section.role, minimal_evidence: section.minimal_evidence,
      repair_packet: section.repair_packet, note: section.note,
    }])),
  }]));
}

function allExpertLabelsOnly(annotations) {
  return Object.fromEntries(Object.entries(annotations).map(([expertId, labels]) => [expertId, labelsOnly(labels)]));
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.ANNOTATION_CHROMIUM_PATH ? { executablePath: process.env.ANNOTATION_CHROMIUM_PATH } : {}),
  });
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'sa-mcgs-assisted-qa-'));
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, offline: true });
    const page = await context.newPage();
    const errors = [];
    const remoteRequests = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    page.on('request', (request) => { if (/^https?:/.test(request.url())) remoteRequests.push(request.url()); });
    page.on('dialog', (dialog) => dialog.accept());
    await page.goto(pathToFileURL(htmlPath).href);
    await page.locator('.algorithm-hints').first().waitFor();
    assert.match(await page.title(), /辅助/);
    assert.equal(await page.locator('.paragraph-card').count() * 4, await page.locator('.model-hint').count());
    await page.evaluate(() => {
      const index = casesForExpert().findIndex((item) => item.presentation_id === 'P-1FB71850B0');
      if (index < 0) throw new Error('Screenshot sample is missing');
      navigateTo(index);
    });
    const screenshotSaCard = page.locator('[data-section-id="S003"] .method-hint-card').filter({ has: page.locator('h5', { hasText: 'SA-MCGS' }) });
    assert.equal(await screenshotSaCard.locator('.model-hint').count(), 2);
    assert.equal(await screenshotSaCard.locator('.unavailable').count(), 0, 'The screenshot sample must now show both successful retry results');
    assert.match(await screenshotSaCard.textContent(), /排名/);
    await screenshotSaCard.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(artifacts, 'updated-pre-s003.png') });
    const preValidity = await page.evaluate(() => {
      const pre = Object.values(state.hints.cases).filter((item) => item.condition === 'pre');
      return Object.fromEntries(['gpt-4o', 'gemini-2.5-pro'].map((model) => [model,
        pre.filter((item) => Object.values(item.sections).every((section) => section.methods['sa-mcgs'].models[model].status === 'available')).length,
      ]));
    });
    assert.deepEqual(preValidity, { 'gpt-4o': 15, 'gemini-2.5-pro': 18 });
    await page.locator('#reviewerId').fill('TEST-ONLY-BROWSER');
    await page.locator('.paragraph-card').first().locator('input[value="ordinary_context"]').check();
    await page.locator('.paragraph-card').first().locator('[data-section-note]').fill('TEST-ONLY-NOTE');
    await page.waitForFunction(() => annotationFor(currentCase().presentation_id).sections?.[currentCase().sections[0].section_id]?.note === 'TEST-ONLY-NOTE');
    await page.reload();
    assert.equal(await page.locator('#reviewerId').inputValue(), 'TEST-ONLY-BROWSER');
    assert.equal(await page.locator('.paragraph-card').first().locator('[data-section-note]').inputValue(), 'TEST-ONLY-NOTE');
    await page.locator('#toggleHintsBtn').click();
    assert.equal(await page.locator('.algorithm-hints:visible').count(), 0);
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem(storeKey())).annotation_mode), 'method_assisted_review');
    await page.locator('#toggleHintsBtn').click();
    await page.evaluate(() => {
      const postIndex = casesForExpert().findIndex((item) => state.hints.cases[item.presentation_id].condition === 'post');
      navigateTo(postIndex);
      window.scrollTo(0, 300);
    });
    assert.match(await page.locator('.sample-condition').textContent(), /注入后/);
    await page.screenshot({ path: path.join(artifacts, 'desktop.png') });

    for (const [button, extension] of [['exportJsonBtn', 'json'], ['exportCsvBtn', 'csv'], ['exportXlsxBtn', 'xlsx']]) {
      const [download] = await Promise.all([page.waitForEvent('download'), page.locator(`#${button}`).click()]);
      assert.ok(download.suggestedFilename().endsWith(`.${extension}`));
      assert.match(download.suggestedFilename(), /辅助复核/);
      const bytes = fs.readFileSync(await download.path());
      assert.ok(bytes.length > 0);
      if (extension === 'json') {
        const payload = JSON.parse(bytes.toString('utf8'));
        assert.equal(payload.annotation_mode, 'method_assisted_review');
        assert.equal(payload.hint_pack_hash, hints.hint_pack_hash);
        assert.ok(payload.hint_pack_history.includes(hints.hint_pack_hash));
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.algorithm-hints').first().scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page overflows horizontally');
    await page.screenshot({ path: path.join(artifacts, 'mobile.png') });
    assert.deepEqual(errors, []);
    assert.deepEqual(remoteRequests, [], 'Offline page attempted a network request');

    // Migration uses synthetic data in a second disposable browser context.
    const migrationContext = await browser.newContext({ offline: true });
    const migration = await migrationContext.newPage();
    const oldKey = `sa_mcgs_blind_expert_audit_v2:${manifest.study_id}:${manifest.manifest_hash}`;
    const oldRaw = JSON.stringify({
      schema_version: 'blind_annotation.state.v2', annotation_mode: 'blind_human_audit',
      study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      translation_pack_hash: translations.translation_pack_hash,
      orders: manifest.expert_orders, annotations: {}, reviewer_ids: { expert_1: 'TEST-ONLY-LEGACY' },
      active_expert: 'expert_1', active_indices: { expert_1: 3 },
    });
    await migration.addInitScript(({ key, raw }) => localStorage.setItem(key, raw), { key: oldKey, raw: oldRaw });
    await migration.goto(pathToFileURL(htmlPath).href);
    await migration.locator('.algorithm-hints').first().waitFor();
    assert.equal(await migration.locator('#reviewerId').inputValue(), 'TEST-ONLY-LEGACY');
    assert.equal(await migration.evaluate(() => state.activeIndex), 3);
    assert.equal(await migration.evaluate((key) => localStorage.getItem(key), oldKey), oldRaw);
    assert.equal(await migration.locator('#migrationNotice').isVisible(), true);

    // A previous assisted snapshot has precedence over blind fallback. Every
    // expert's synthetic labels must survive without rewriting either old key.
    const assistedContext = await browser.newContext({ offline: true });
    const assisted = await assistedContext.newPage();
    assisted.on('dialog', (dialog) => dialog.accept());
    const assistedKey = `sa_mcgs_assisted_expert_audit_v1:${manifest.study_id}:${manifest.manifest_hash}:${previousHash}`;
    const oldAssisted = {
      schema_version: 'assisted_standalone_annotation.state.v1', annotation_mode: 'method_assisted_review',
      study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      translation_pack_hash: translations.translation_pack_hash, hint_pack_hash: previousHash,
      hints_visible: false, progress_origin: 'existing_assisted_session',
      orders: manifest.expert_orders,
      annotations: Object.fromEntries(['expert_1', 'expert_2', 'expert_3'].map((id) => [id, syntheticAnnotations(id)])),
      reviewer_ids: { expert_1: 'TEST-OLD-1', expert_2: 'TEST-OLD-2', expert_3: 'TEST-OLD-3' },
      active_expert: 'expert_3', active_indices: { expert_1: 2, expert_2: 5, expert_3: 8 },
    };
    const oldAssistedRaw = JSON.stringify(oldAssisted);
    await assisted.addInitScript((records) => {
      for (const [key, raw] of records) localStorage.setItem(key, raw);
    }, [[oldKey, oldRaw], [assistedKey, oldAssistedRaw]]);
    await assisted.goto(pathToFileURL(htmlPath).href);
    await assisted.locator('.algorithm-hints').first().waitFor({ state: 'attached' });
    assert.equal(await assisted.locator('#reviewerId').inputValue(), 'TEST-OLD-3');
    assert.equal(await assisted.evaluate(() => state.activeIndex), 8);
    assert.equal(await assisted.locator('.algorithm-hints:visible').count(), 0);
    assert.deepEqual(allExpertLabelsOnly(await assisted.evaluate(() => state.annotations)), allExpertLabelsOnly(oldAssisted.annotations));
    assert.equal(await assisted.evaluate((key) => localStorage.getItem(key), assistedKey), oldAssistedRaw);
    assert.equal(await assisted.evaluate((key) => localStorage.getItem(key), oldKey), oldRaw);
    assertHintHistory(await assisted.evaluate(() => state.hintPackHistory));
    assertHintHistory(await assisted.evaluate(() => JSON.parse(localStorage.getItem(storeKey())).hint_pack_history));
    await assisted.reload();
    assert.deepEqual(allExpertLabelsOnly(await assisted.evaluate(() => state.annotations)), allExpertLabelsOnly(oldAssisted.annotations));
    assertHintHistory(await assisted.evaluate(() => state.hintPackHistory));
    const oldBackup = {
      schema_version: 'assisted_standalone_annotation.export.v1', annotation_mode: 'method_assisted_review',
      study_id: manifest.study_id, manifest_hash: manifest.manifest_hash,
      translation_pack_hash: translations.translation_pack_hash, hint_pack_hash: previousHash,
      expert_slot: 'expert_1', anonymous_reviewer_id: 'TEST-IMPORTED-OLD',
      order: manifest.expert_orders.expert_1, active_index: 4,
      annotations: syntheticAnnotations('expert_1'), exported_at: '2000-01-01T00:00:00.000Z',
    };
    oldBackup.annotations[manifest.expert_orders.expert_1[0]].comments = 'TEST-IMPORTED-LABEL';
    await assisted.evaluate(async (backup) => restoreBackup(backup), oldBackup);
    assert.equal(await assisted.locator('#reviewerId').inputValue(), 'TEST-IMPORTED-OLD');
    assert.equal(await assisted.evaluate(() => state.activeIndex), 4);
    assert.deepEqual(labelsOnly(await assisted.evaluate(() => state.annotations.expert_1)), labelsOnly(oldBackup.annotations));
    assert.deepEqual(labelsOnly(await assisted.evaluate(() => state.annotations.expert_2)), labelsOnly(oldAssisted.annotations.expert_2));
    assert.deepEqual(labelsOnly(await assisted.evaluate(() => state.annotations.expert_3)), labelsOnly(oldAssisted.annotations.expert_3));
    const beforeUnknownImport = await assisted.evaluate(() => JSON.stringify(state));
    const rejected = await assisted.evaluate(async (backup) => {
      try { await restoreBackup(backup); return ''; } catch (error) { return error.message; }
    }, { ...oldBackup, hint_pack_hash: `sha256:${'0'.repeat(64)}` });
    assert.match(rejected, /提示|版本|匹配/);
    assert.equal(await assisted.evaluate(() => JSON.stringify(state)), beforeUnknownImport);
    const [migratedDownload] = await Promise.all([assisted.waitForEvent('download'), assisted.locator('#exportJsonBtn').click()]);
    const migratedExport = JSON.parse(fs.readFileSync(await migratedDownload.path(), 'utf8'));
    assert.equal(migratedExport.hint_pack_hash, hints.hint_pack_hash);
    assert.deepEqual(labelsOnly(migratedExport.annotations), labelsOnly(oldBackup.annotations));
    assertHintHistory(migratedExport.hint_pack_history);
    assert.equal(await assisted.evaluate((key) => localStorage.getItem(key), assistedKey), oldAssistedRaw);
    assert.equal(await assisted.evaluate((key) => localStorage.getItem(key), oldKey), oldRaw);
    console.log(JSON.stringify({ status: 'pass', offline: true, persistence: true, legacyCopy: true,
      septemberPreValidity: preValidity, screenshotRegression: true, oldAssistedCopy: true,
      oldAssistedJsonImport: true, hintHistoryRetained: true,
      exports: ['json', 'csv', 'xlsx'], mobileOverflow: false, artifacts }, null, 2));
  } finally {
    await browser.close();
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
