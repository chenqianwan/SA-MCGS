#!/usr/bin/env node
'use strict';

// Synthetic-data QA in a disposable Playwright context. Never visits the real
// user browser or reads its storage, and never writes any source annotations.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = path.resolve(__dirname, '..');
// Keep the original truly blind package under regression after the main
// filename becomes a hint-enabled page. The two modes have separate tests.
const blindBackup = path.join(root, 'dist', '第三专家_独立盲评.original.html');
const htmlPath = process.argv[2] || (fs.existsSync(blindBackup) ? blindBackup : path.join(root, 'dist', '第三专家_独立盲评.html'));
const html = fs.readFileSync(htmlPath, 'utf8');
const load = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const manifest = load(path.join(root, 'data/manifest.json'));
const translations = load(path.join(root, 'data/translations_zh.json'));
const parentManifest = load(path.join(root, '../frontend/data/manifest.json'));
const parentTranslations = load(path.join(root, '../frontend/data/translations_zh.json'));
const embed = (id) => JSON.parse(html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`))[1]);
const clone = (v) => JSON.parse(JSON.stringify(v));
const stable = (v) => { const out = clone(v); delete out.exported_at; return out; };
assert.deepEqual(embed('manifestData'), manifest);
assert.deepEqual(embed('translationData'), translations);
assert.equal(manifest.cases.length, 14);
assert.equal(manifest.cases.reduce((n, c) => n + c.sections.length, 0), 264);
assert.deepEqual(Object.keys(manifest.expert_orders), ['expert_3']);
assert.deepEqual(manifest.expert_orders.expert_3, parentManifest.expert_orders.expert_3.filter((id) => manifest.cases.some((c) => c.presentation_id === id)));
for (const item of manifest.cases) {
  assert.deepEqual(item, parentManifest.cases.find((c) => c.presentation_id === item.presentation_id));
  for (const section of item.sections) {
    const prior = parentTranslations.cases[item.presentation_id].sections[section.section_id];
    assert.deepEqual(translations.cases[item.presentation_id].sections[section.section_id], { title_zh: prior.title_zh || '', text_zh: prior.text_zh || '' });
  }
}
for (const forbidden of ['methodHintsData', 'injectionMarkersData', 'source_physical_fingerprint', 'minimal_jaccard', 'repair_jaccard', 'target_disagreement', '"expert_1"', '"expert_2"', '"injection_identity":']) {
  assert.ok(!html.includes(forbidden), `Private data leaked in HTML: ${forbidden}`);
}
assert.ok(!JSON.stringify({ manifest, translations }).includes('"condition":'), 'Data payload must not identify pre/post conditions');

async function main() {
  const artifacts = fs.mkdtempSync(path.join(os.tmpdir(), 'sa-mcgs-third-blind-qa-'));
  const browser = await chromium.launch({ headless: true, ...(process.env.ANNOTATION_CHROMIUM_PATH ? { executablePath: process.env.ANNOTATION_CHROMIUM_PATH } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, offline: true, acceptDownloads: true });
    const page = await context.newPage();
    const remoteRequests = [], errors = [], dialogs = [];
    page.on('request', (r) => { if (/^https?:/.test(r.url())) remoteRequests.push(r.url()); });
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('dialog', async (d) => { dialogs.push(d.message()); await d.accept(); });
    // Old progress is synthetic and must never migrate to the third-rater page.
    const oldKey = `sa_mcgs_blind_expert_audit_v2:${parentManifest.study_id}:${parentManifest.manifest_hash}`;
    const oldRaw = JSON.stringify({ active_expert: 'expert_1', reviewer_ids: { expert_1: 'TEST-OLD-DO-NOT-IMPORT' }, annotations: { expert_1: { OLD: { target_conflict: 'present' } } } });
    await page.addInitScript(({ k, v }) => localStorage.setItem(k, v), { k: oldKey, v: oldRaw });
    await page.goto(pathToFileURL(htmlPath).href);
    await page.waitForFunction(() => !!window.ThirdExpertReview);
    assert.equal(await page.locator('#reviewerId').inputValue(), '');
    assert.equal(await page.locator('#progressText').textContent(), '0 / 14');
    assert.equal(await page.locator('[name="target_conflict"]:checked').count(), 0);
    assert.equal(await page.locator('[name="judgment_sufficient"]:checked').count(), 0);
    assert.deepEqual(await page.evaluate(() => ThirdExpertReview.getSnapshot().annotations), {});
    assert.equal(await page.evaluate((k) => localStorage.getItem(k), oldKey), oldRaw);
    assert.match(await page.title(), /专家 3.*独立盲法/);
    assert.equal(await page.locator('.algorithm-hints, .injection-marker, .sample-condition').count(), 0);
    await page.screenshot({ path: path.join(artifacts, 'desktop-top.png') });
    await page.screenshot({ path: path.join(artifacts, 'desktop-fullpage.png'), fullPage: true });
    const first = manifest.cases[0], second = manifest.cases[1];
    const firstSection = first.sections[0].section_id;
    assert.equal(await page.locator('.paragraph-card').count(), first.sections.length);
    assert.equal(await page.locator('.paragraph-body').first().textContent(), translations.cases[first.presentation_id].sections[firstSection].text_zh);

    // Draft export keeps all question labels blank; no manufactured positives.
    const blankRows = await page.evaluate(() => ThirdExpertReview.buildExportRows());
    assert.equal(blankRows.caseRows.length, 14); assert.equal(blankRows.sectionRows.length, 264);
    assert.ok(blankRows.caseRows.every((r) => r.目标冲突代码 === '' && r.judgment_sufficient === '' && r.判断信心_1到5 === '' && r.sets_reviewed === false && r.scoring_eligibility === 'pending'));
    const [blankDownload] = await Promise.all([page.waitForEvent('download'), page.locator('#exportJsonBtn').click()]);
    const blankBackup = JSON.parse(fs.readFileSync(await blankDownload.path(), 'utf8'));
    assert.deepEqual(blankBackup.annotations, {});
    assert.equal(await page.evaluate((r) => ThirdExpertReview.validateBackup(r), blankBackup), true);

    await page.locator('#reviewerId').fill('TEST-ONLY-EXPERT3');
    await page.locator('[name="target_conflict"][value="present"]').check();
    await page.locator('[name="judgment_sufficient"][value="yes"]').check();
    await page.locator('[name="confidence"]').selectOption('4');
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), false);
    assert.match(await page.locator('#validationBox').textContent(), /非空最小证据/);
    const card = page.locator('.paragraph-card').first();
    await card.locator('[data-minimal-evidence]').check();
    assert.equal(await card.locator('[data-repair-packet]').isChecked(), true);
    await card.locator('[data-repair-packet]').click();
    assert.equal(await card.locator('[data-repair-packet]').isChecked(), true, 'M must stay a subset of R');
    await page.locator('#caseList [data-index="1"]').click();
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), false, 'Navigation cannot confirm a draft');
    await page.locator('#caseList [data-index="0"]').click();
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), true);
    assert.equal(await page.locator('#progressText').textContent(), '1 / 14');
    await page.locator('[name="comments"]').fill('TEST-ONLY: independent synthetic judgment');
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), false, 'An edit must revoke confirmation');
    await page.locator('#saveCurrentBtn').click();
    await page.reload(); await page.waitForFunction(() => !!window.ThirdExpertReview);
    assert.equal(await page.locator('#reviewerId').inputValue(), 'TEST-ONLY-EXPERT3');
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), true);
    await page.locator('#caseList [data-index="1"]').click();
    await page.locator('[name="target_conflict"][value="absent"]').check();
    await page.locator('[name="judgment_sufficient"][value="no"]').check();
    await page.locator('[name="confidence"]').selectOption('2');
    await page.locator('#saveCurrentBtn').click();
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), second.presentation_id), true, 'Insufficient material is a valid completed response');
    assert.equal((await page.evaluate(() => ThirdExpertReview.buildExportRows())).caseRows[1].scoring_eligibility, 'insufficient');
    await page.locator('.paragraph-card').first().locator('[data-minimal-evidence]').check();
    await page.locator('#saveCurrentBtn').click();
    assert.match(await page.locator('#validationBox').textContent(), /不存在冲突/);
    await page.locator('.paragraph-card').first().locator('[data-minimal-evidence]').uncheck();
    await page.locator('.paragraph-card').first().locator('[data-repair-packet]').uncheck();
    await page.locator('#saveCurrentBtn').click();

    // Download real XLSX and parse its bytes with the page's offline vendor.
    const [xlsxDownload] = await Promise.all([page.waitForEvent('download'), page.locator('#exportXlsxBtn').click()]);
    const bytes = fs.readFileSync(await xlsxDownload.path());
    assert.ok(bytes.length > 1000); assert.match(xlsxDownload.suggestedFilename(), /未完成\.xlsx$/);
    const workbook = await page.evaluate((encoded) => {
      const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
      const wb = XLSX.read(bytes, { type: 'array' });
      return { sheets: wb.SheetNames, rows: Object.fromEntries(wb.SheetNames.map((s) => [s, XLSX.utils.sheet_to_json(wb.Sheets[s], { defval: '' })])) };
    }, bytes.toString('base64'));
    assert.deepEqual(workbook.sheets, ['样本整体标注', '逐段标注', '版本信息']);
    assert.equal(workbook.rows.样本整体标注.length, 14); assert.equal(workbook.rows.逐段标注.length, 264); assert.equal(workbook.rows.版本信息.length, 1);
    for (const row of [...workbook.rows.样本整体标注, ...workbook.rows.逐段标注, ...workbook.rows.版本信息]) {
      assert.equal(row.expert_slot, 'expert_3'); assert.equal(row.annotation_protocol, 'binary_judgment_v1');
      assert.equal(row.schema_version, 'third_expert_blind_export.v1');
      assert.equal(row.review_protocol, 'targeted_third_blind_v1'); assert.equal(row.annotation_mode, 'blind_human_audit');
      assert.equal(row.manifest_hash, manifest.manifest_hash); assert.equal(row.parent_manifest_hash, manifest.parent_manifest_hash);
    }
    assert.equal(workbook.rows.版本信息[0].已确认样本数, 2);
    assert.equal(workbook.rows.样本整体标注.filter((r) => r.完成状态 === '已完成').length, 2);
    assert.ok(workbook.rows.样本整体标注.slice(2).every((r) => r.目标冲突代码 === '' && r.judgment_sufficient === '' && r.sets_reviewed === false && r.scoring_eligibility === 'pending'));

    const [jsonDownload] = await Promise.all([page.waitForEvent('download'), page.locator('#exportJsonBtn').click()]);
    const backup = JSON.parse(fs.readFileSync(await jsonDownload.path(), 'utf8'));
    assert.equal(backup.schema_version, 'third_expert_blind_export.v1');
    assert.equal(backup.expert_slot, 'expert_3'); assert.equal(backup.annotation_mode, 'blind_human_audit');
    const invalid = [
      ['old schema', (r) => { r.schema_version = 'assisted_standalone_annotation.export.v1'; }],
      ['wrong hash', (r) => { r.manifest_hash = 'sha256:invalid'; }],
      ['wrong parent hash', (r) => { r.parent_manifest_hash = 'sha256:invalid'; }],
      ['wrong slot', (r) => { r.expert_slot = 'expert_1'; }],
      ['wrong protocol', (r) => { r.annotation_protocol = 'legacy'; }],
      ['assisted mode', (r) => { r.annotation_mode = 'method_assisted_review'; }],
      ['full 42-case order', (r) => { r.order = parentManifest.expert_orders.expert_3; }],
      ['unknown case', (r) => { r.annotations['P-UNKNOWN'] = clone(r.annotations[first.presentation_id]); }],
      ['unknown section', (r) => { r.annotations[first.presentation_id].sections.S999 = { minimal_evidence: false, repair_packet: false, note: '' }; }],
      ['missing section', (r) => { delete r.annotations[first.presentation_id].sections[firstSection]; }],
      ['malformed boolean', (r) => { r.annotations[first.presentation_id].sections[firstSection].minimal_evidence = 'yes'; }],
      ['malformed confirmation', (r) => { r.annotations[first.presentation_id].sets_reviewed = 'true'; }],
      ['broken subset', (r) => { r.annotations[first.presentation_id].sections[firstSection].repair_packet = false; }],
      ['unknown private field', (r) => { r.annotations[first.presentation_id].expert_1_answer = 'present'; }],
      ['incomplete marked confirmed', (r) => { r.annotations[first.presentation_id].target_conflict = ''; }],
    ];
    for (const [name, mutate] of invalid) {
      const input = clone(backup); mutate(input);
      const before = stable(await page.evaluate(() => ThirdExpertReview.getSnapshot()));
      const storageBefore = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));
      const rejected = await page.evaluate((raw) => { try { ThirdExpertReview.restoreBackup(raw); return ''; } catch (e) { return e.message; } }, input);
      assert.ok(rejected, `${name} must be rejected`);
      assert.deepEqual(stable(await page.evaluate(() => ThirdExpertReview.getSnapshot())), before, `${name} changed current state`);
      assert.deepEqual(await page.evaluate(() => Object.fromEntries(Object.entries(localStorage))), storageBefore, `${name} wrote storage before validation`);
    }
    const draft = clone(backup);
    draft.annotations[first.presentation_id].target_conflict = '';
    draft.annotations[first.presentation_id].sets_reviewed = false;
    assert.equal(await page.evaluate((raw) => ThirdExpertReview.restoreBackup(raw), draft), true);
    assert.equal(await page.evaluate((id) => ThirdExpertReview.isComplete(id), first.presentation_id), false);
    assert.equal(await page.evaluate((raw) => ThirdExpertReview.restoreBackup(raw), backup), true);
    assert.deepEqual(stable(await page.evaluate(() => ThirdExpertReview.getSnapshot())), stable(backup));
    assert.equal(await page.evaluate((k) => localStorage.getItem(k), oldKey), oldRaw);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#caseList [data-index="0"]').click();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile horizontal overflow');
    await page.screenshot({ path: path.join(artifacts, 'mobile-top.png') });
    assert.deepEqual(errors, []); assert.deepEqual(remoteRequests, []);
    // Some file:// browsers block storage. The page must still be usable and
    // export its in-memory work, without silently losing existing drafts.
    const restrictedContext = await browser.newContext({ offline: true, acceptDownloads: true });
    const restricted = await restrictedContext.newPage();
    restricted.on('dialog', (dialog) => dialog.accept());
    await restricted.addInitScript(() => Object.defineProperty(window, 'localStorage', {
      get() { throw new DOMException('Test-only disabled storage', 'SecurityError'); },
    }));
    await restricted.goto(pathToFileURL(htmlPath).href);
    await restricted.waitForFunction(() => !!window.ThirdExpertReview);
    assert.match(await restricted.locator('#saveStatus').textContent(), /存储不可用/);
    assert.equal(await restricted.locator('.paragraph-card').count(), first.sections.length);
    await restricted.locator('#reviewerId').fill('TEST-ONLY-NO-STORAGE');
    await restricted.locator('[name="target_conflict"][value="absent"]').check();
    const [restrictedDownload] = await Promise.all([restricted.waitForEvent('download'), restricted.locator('#exportJsonBtn').click()]);
    const restrictedBackup = JSON.parse(fs.readFileSync(await restrictedDownload.path(), 'utf8'));
    assert.equal(restrictedBackup.annotations[first.presentation_id].target_conflict, 'absent');
    const restrictedBefore = stable(await restricted.evaluate(() => ThirdExpertReview.getSnapshot()));
    const restrictedReject = await restricted.evaluate((raw) => { try { ThirdExpertReview.restoreBackup(raw); return ''; } catch (e) { return e.message; } }, backup);
    assert.ok(restrictedReject, 'Must not overwrite in-memory work without a safe archive');
    assert.deepEqual(stable(await restricted.evaluate(() => ThirdExpertReview.getSnapshot())), restrictedBefore);
    await restrictedContext.close();
    console.log(JSON.stringify({ status: 'pass', cases: 14, sections: 264, selectedTextUnchanged: true,
      blindedEmbeddedPayload: true, isolatedStorage: true, offlineNetworkRequests: 0,
      incompleteDrafts: true, explicitConfirmation: true, editInvalidation: true,
      malformedRestoreRejections: invalid.length, xlsxRows: { cases: 14, sections: 264, metadata: 1 },
      blankUnvisitedQuestions: true, storageDisabledStillEditableAndExportable: true, screenshots: artifacts }, null, 2));
  } finally { await browser.close(); }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
