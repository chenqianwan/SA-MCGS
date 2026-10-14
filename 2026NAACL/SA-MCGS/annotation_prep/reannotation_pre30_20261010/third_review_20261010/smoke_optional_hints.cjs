'use strict';
// Synthetic annotations and isolated browser contexts only; no live user storage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = __dirname, parent = path.dirname(root), out = path.join(root, 'qa');
const data = JSON.parse(fs.readFileSync(path.join(root, 'payload.json'), 'utf8'));
const hints = JSON.parse(fs.readFileSync(path.join(root, 'method_hints_with_predictions.json'), 'utf8'));
const parentData = JSON.parse(fs.readFileSync(path.join(parent, 'payload.json'), 'utf8'));
const audit = JSON.parse(fs.readFileSync(path.join(root, 'internal/selection_audit.json'), 'utf8'));
const oldDir = path.join(out, 'optional_hints_before');
const oldData = JSON.parse(fs.readFileSync(path.join(oldDir, 'payload.json'), 'utf8'));
const oldHtml = fs.readFileSync(path.join(oldDir, 'dist/expert3_blind_20261010.html'), 'utf8');
const newHtml = fs.readFileSync(path.join(parent, 'dist/expert3_blind_20261010.html'), 'utf8');
const url = 'http://optional-hints.test/expert3_blind_20261010.html';
const storageKey = `third_expert_blind_v1:${data.study_id}:${data.manifest_hash}:expert_3`;
const clone = value => JSON.parse(JSON.stringify(value));
const sorted = value => [...value].sort();
async function downloaded(page, selector) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
  return fs.readFileSync(await download.path(), 'utf8');
}
const exported = async page => JSON.parse(await downloaded(page, '#exportJsonBtn'));
const stored = page => page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));
function parseCsv(text) {
  const rows = []; let row = [], field = '', quoted = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i += 1; } else quoted = !quoted;
    } else if (char === ',' && !quoted) { row.push(field); field = ''; }
    else if ((char === '\r' || char === '\n') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += char;
  }
  assert.equal(quoted, false);
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const columns = rows.shift();
  return {columns, rows:rows.map(values => {
    assert.equal(values.length, columns.length);
    return Object.fromEntries(columns.map((column, index) => [column, values[index]]));
  })};
}
function assertVisibility(backup, visible, seen) {
  assert.equal(backup.hints_visible, visible);
  assert.equal(backup.hint_visibility.ever_shown, seen.length > 0);
  assert.deepEqual(sorted(backup.hint_visibility.shown_case_ids), sorted(seen));
  assert(Array.isArray(backup.hint_visibility.events));
  assert.equal(backup.annotation_mode, seen.length ? 'method_assisted_review' : 'blind');
  assert.equal(backup.hint_visibility.pack_hash, hints.pack_hash);
  if (!seen.length) assert.deepEqual(backup.hint_visibility.events, []);
}
function assertHistoryRetained(before, after) {
  assert(after.hint_visibility.ever_shown);
  for (const id of before.hint_visibility.shown_case_ids) assert(after.hint_visibility.shown_case_ids.includes(id));
  const current = new Set(after.hint_visibility.events.map(event => JSON.stringify(event)));
  for (const event of before.hint_visibility.events) assert(current.has(JSON.stringify(event)), 'A previously recorded exposure event must survive');
  assert.equal(after.annotation_mode, 'method_assisted_review');
}
async function importBackup(page, backup, name) {
  await page.locator('#importFile').setInputFiles({name, mimeType:'application/json', buffer:Buffer.from(JSON.stringify(backup))});
  await page.waitForFunction(() => document.querySelector('#saveStatus').textContent.includes('备份已恢复'));
  return exported(page);
}

async function main() {
  assert.deepEqual(data, oldData, 'Core materials and identity are unchanged');
  assert.equal(data.case_count, 5);
  assert.equal(data.cases.reduce((sum, item) => sum + item.sections.length, 0), 78);
  assert.equal(hints.schema_version, 'third_expert_method_hints.v2');
  assert.equal(hints.source_manifest_hash, data.manifest_hash);
  assert.deepEqual(hints.methods, ['sa-mcgs','lea']);
  assert.deepEqual(sorted(Object.keys(hints.cases)), sorted(data.cases.map(item => item.id)));
  assert.deepEqual(sorted(Object.keys(hints.case_predictions)), sorted(data.cases.map(item => item.id)));
  assert.equal(typeof hints.risk_rule_description, 'string');
  assert(hints.risk_rule_description.trim());
  const predictionFields = ['model','label','status','risk_found','risk_pair_count','reason','evidence_sections','decision_rule'];
  let expectedRows = 0;
  for (const item of data.cases) {
    const sourceId = audit.blind_mapping[item.id].case_id;
    assert.deepEqual(hints.cases[item.id], parentData.node_results[sourceId], `Hints are the exact retained source for ${item.id}`);
    assert.deepEqual(sorted(Object.keys(hints.cases[item.id])), sorted(item.sections.map(section => section.id)));
    const sourceCase = parentData.cases.find(candidate => candidate.id === sourceId);
    const sourcePredictions = sourceCase.sa_predictions.map(prediction => Object.fromEntries(predictionFields.map(field => [field, prediction[field]])));
    assert.deepEqual(hints.case_predictions[item.id], sourcePredictions, `Case predictions equal the approved public source fields for ${item.id}`);
    for (const prediction of hints.case_predictions[item.id]) assert.deepEqual(sorted(Object.keys(prediction)), sorted(predictionFields));
    expectedRows += item.sections.length * hints.methods.length * hints.models.length;
  }
  assert.equal(expectedRows, 312);
  const packedHints = JSON.stringify(hints);
  for (const pattern of [/PRE-\d{2}/, /expert_[12]\b/, /original_ratings/, /historical_annotations/,
    /historical_import/, /source_presentation_id/, /selection_reason/, /result_path/, /\/Users\//,
    /experiments\//, /pre_(?:sec_ex21|cuad|bgb)_/]) assert(!pattern.test(packedHints), `Hint pack leaks private metadata: ${pattern}`);
  for (const pattern of [/PRE-\d{2}/, /expert_[12]\b/, /original_ratings/, /historical_annotations/,
    /historical_import/, /source_presentation_id/, /selection_reason/]) {
    assert(!pattern.test(newHtml), `Public HTML leaks prohibited human review metadata: ${pattern}`);
  }
  assert.equal(fs.readFileSync(path.join(parent, 'dist/pre30_reannotation.html'), 'utf8'), newHtml);
  const browser = await chromium.launch({headless:true, executablePath:process.env.ANNOTATION_CHROMIUM_PATH});
  const contexts = [], errors = [], unexpectedRequests = [];
  async function harness(initialHtml) {
    let html = initialHtml;
    const context = await browser.newContext({viewport:{width:1600,height:1100}, reducedMotion:'reduce'});
    contexts.push(context);
    await context.route('**/*', route => {
      if (route.request().url() === url && route.request().resourceType() === 'document') {
        return route.fulfill({contentType:'text/html', body:html});
      }
      unexpectedRequests.push(route.request().url()); return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('dialog', dialog => dialog.accept());
    return {context, page, setHtml:value => { html = value; }};
  }
  try {
    // Fresh defaults and screenshots contain no synthetic human answers.
    const fresh = await harness(newHtml), preview = fresh.page;
    await preview.goto(url);
    await preview.locator('#app').waitFor({state:'visible'});
    assert.equal(await preview.locator('.model-hint').count(), 0);
    assert.equal(await preview.locator('.prediction-area').count(), 0);
    assert.equal(await preview.locator('#toggleHintsBtn').count(), 1);
    assert.deepEqual(JSON.parse(await preview.locator('#payloadData').textContent()), data);
    assert.deepEqual(JSON.parse(await preview.locator('#methodHintsData').textContent()), hints);
    const initial = await exported(preview);
    assert.deepEqual(initial.annotations, {});
    assertVisibility(initial, false, []);
    await preview.screenshot({path:path.join(out, 'optional_hints_default.png')});
    await preview.locator('#toggleHintsBtn').click();
    assert((await preview.locator('.model-hint').count()) > 0);
    assert.equal(await preview.locator('.prediction-area .prediction-card[data-model]').count(), 2);
    assert.deepEqual((await exported(preview)).annotations, {});
    await preview.locator('.prediction-area').scrollIntoViewIfNeeded();
    await preview.screenshot({path:path.join(out, 'optional_hints_case_predictions.png')});
    await preview.locator('.material-section').first().scrollIntoViewIfNeeded();
    await preview.screenshot({path:path.join(out, 'optional_hints_shown.png')});
    await preview.setViewportSize({width:390,height:844});
    await preview.locator('.material-section').first().scrollIntoViewIfNeeded();
    await preview.screenshot({path:path.join(out, 'optional_hints_mobile.png')});
    assert(await preview.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));

    // Previous v2 answers and events remain valid when the optional hint pack changes.
    const previousV2Html = fs.readFileSync(path.join(out, 'case_predictions_before/expert3_blind_20261010.html'), 'utf8');
    const packUpgrade = await harness(previousV2Html);
    await packUpgrade.page.goto(url);
    await packUpgrade.page.locator('input[name="confidence"][value="2"]').check();
    await packUpgrade.page.locator('#notesInput').fill('SYNTHETIC previous v2 draft across hint-pack update');
    await packUpgrade.page.locator('#toggleHintsBtn').click();
    const beforePackUpgrade = await exported(packUpgrade.page);
    assert.notEqual(beforePackUpgrade.hint_visibility.pack_hash, hints.pack_hash);
    packUpgrade.setHtml(newHtml); await packUpgrade.page.reload();
    const afterPackUpgrade = await exported(packUpgrade.page);
    assert.deepEqual(afterPackUpgrade.annotations, beforePackUpgrade.annotations);
    assertHistoryRetained(beforePackUpgrade, afterPackUpgrade);
    assert.equal(afterPackUpgrade.hints_visible, false);
    assert.equal(afterPackUpgrade.hint_visibility.pack_hash, hints.pack_hash);
    assert.equal(await packUpgrade.page.locator('.prediction-area').count(), 0);

    // Seed real v1 storage via the archived UI: one confirmed case and one draft.
    const upgrade = await harness(oldHtml), page = upgrade.page;
    const firstId = data.cases[0].id, secondId = data.cases[1].id;
    await page.goto(url);
    await page.locator('input[name="target_conflict"][value="present"]').check();
    await page.locator('input[name="judgment_sufficient"][value="sufficient"]').check();
    await page.locator('input[name="confidence"][value="4"]').check();
    await page.locator('input[data-section-id="S001"][data-field="minimal_evidence"]').check();
    await page.locator('#notesInput').fill('SYNTHETIC confirmed v1 annotation: preserve the full record');
    await page.locator('#confirmBtn').click();
    await page.locator(`[data-case="${secondId}"]`).click();
    await page.locator('input[name="target_conflict"][value="absent"]').check();
    await page.locator('input[name="judgment_sufficient"][value="insufficient"]').check();
    await page.locator('input[name="confidence"][value="2"]').check();
    await page.locator('#notesInput').fill('SYNTHETIC draft v1 annotation: do not confirm or reset');
    const legacy = await exported(page), oldStorage = await stored(page);
    assert.equal(legacy.schema_version, 'third_expert_blind.export.v1');
    assert.equal(legacy.annotations[firstId].confirmed, true);
    assert.equal(legacy.annotations[secondId].confirmed, false);
    assert(oldStorage[storageKey]);
    upgrade.setHtml(newHtml); await page.reload();
    const earlyV2 = await exported(page);
    assert.equal(earlyV2.schema_version, 'third_expert_blind.export.v2');
    assert.deepEqual(earlyV2.annotations, legacy.annotations);
    assertVisibility(earlyV2, false, []);
    assert.equal(await page.locator('.model-hint').count(), 0);

    // Hidden navigation does not log exposure. Showing and navigating cannot change answers.
    await page.locator(`[data-case="${firstId}"]`).click();
    assertVisibility(await exported(page), false, []);
    await page.locator('#toggleHintsBtn').click();
    assertVisibility(await exported(page), true, [firstId]);
    await page.locator('#toggleHintsBtn').click();
    await page.locator(`[data-case="${secondId}"]`).click();
    assertVisibility(await exported(page), false, [firstId]);
    await page.locator('#toggleHintsBtn').click();
    assertVisibility(await exported(page), true, [firstId,secondId]);
    let checkedRows = 0, checkedPredictions = 0;
    for (const item of data.cases) {
      await page.locator(`[data-case="${item.id}"]`).click();
      assert.equal(await page.locator('.prediction-area').count(), 1);
      assert.equal(await page.locator('.prediction-area .prediction-card[data-model]').count(), hints.models.length);
      for (const prediction of hints.case_predictions[item.id]) {
        const card = page.locator(`.prediction-area .prediction-card[data-model="${prediction.model}"]`);
        const status = prediction.status === 'pending' ? '待运行' : prediction.status !== 'available'
          ? '无有效结果' : prediction.risk_found === true ? '有风险' : '未判风险';
        assert.equal(await card.locator('.prediction-status').innerText(), status);
        const text = await card.textContent();
        if (prediction.status === 'available') assert(new RegExp(`风险对[：:\\s]+${prediction.risk_pair_count}(?!\\d)`).test(text));
        assert.deepEqual(sorted(new Set(text.match(/\bS\d{3}\b/g) || [])), sorted(prediction.evidence_sections));
        checkedPredictions += 1;
      }
      const displayed = await page.locator('.material-section').evaluateAll(sections => sections.map(section => ({
        id:section.dataset.section,
        rows:Array.from(section.querySelectorAll('.model-hint')).map(row => ({
          method:row.closest('[data-method]').dataset.method, model:row.dataset.model,
          unavailable:row.classList.contains('unavailable'), text:row.innerText,
        })),
      })));
      for (const section of displayed) {
        assert.equal(section.rows.length, 4);
        for (const row of section.rows) {
          const expected = hints.cases[item.id][section.id].methods[row.method].models[row.model];
          if (expected.status === 'available') {
            assert.equal(row.unavailable, false);
            assert(row.text.includes(expected.selected ? '已纳入结果子图' : '未纳入结果子图'));
            assert(row.text.includes(`风险相关分 ${expected.score === null ? '—' : expected.score.toFixed(3)}`));
            if (expected.rank !== null) assert(row.text.includes(`第 ${expected.rank} / ${expected.total_nodes}`));
          } else {
            assert.equal(row.unavailable, true);
            assert(!row.text.includes('未纳入结果子图'));
            assert(row.text.includes(expected.status === 'not_run' ? '尚未运行' : '无有效结果'));
          }
          checkedRows += 1;
        }
      }
      assert.deepEqual((await exported(page)).annotations, legacy.annotations);
    }
    assert.equal(checkedRows, expectedRows);
    assert.equal(checkedPredictions, data.case_count * hints.models.length);
    const allSeen = data.cases.map(item => item.id);
    const allShown = await exported(page);
    assertVisibility(allShown, true, allSeen);
    assert(allShown.hint_visibility.events.length > 0);
    await page.locator('#toggleHintsBtn').click();
    const hidden = await exported(page);
    assertVisibility(hidden, false, allSeen);
    assertHistoryRetained(allShown, hidden);
    assert.equal(await page.locator('.model-hint').count(), 0);
    assert.equal(await page.locator('.prediction-area').count(), 0);
    await page.reload();
    const hiddenReload = await exported(page);
    assertVisibility(hiddenReload, false, allSeen);
    assertHistoryRetained(hidden, hiddenReload);
    assert.deepEqual(hiddenReload.annotations, legacy.annotations);
    await page.locator('#toggleHintsBtn').click();
    const beforeOpenReload = await exported(page);
    await page.reload();
    const afterOpenReload = await exported(page);
    assertVisibility(afterOpenReload, false, allSeen);
    assertHistoryRetained(beforeOpenReload, afterOpenReload);
    assert.deepEqual(afterOpenReload.annotations, legacy.annotations);
    assert.equal(await page.locator('.model-hint').count(), 0);
    assert.equal(await page.locator('.prediction-area').count(), 0);

    // Neither an old v1 nor a pre-exposure v2 backup can erase exposure history.
    const importedLegacy = await importBackup(page, legacy, 'synthetic_legacy_v1.json');
    assert.deepEqual(importedLegacy.annotations, legacy.annotations);
    assertHistoryRetained(afterOpenReload, importedLegacy);
    assertVisibility(importedLegacy, false, allSeen);
    const importedEarly = await importBackup(page, earlyV2, 'synthetic_early_v2.json');
    assert.deepEqual(importedEarly.annotations, legacy.annotations);
    assertHistoryRetained(importedLegacy, importedEarly);
    assertVisibility(importedEarly, false, allSeen);
    // Import also keeps exposure added to current storage by another open tab.
    const otherTab = await upgrade.context.newPage();
    otherTab.on('pageerror', error => errors.push(String(error)));
    await otherTab.goto(url);
    await otherTab.locator(`[data-case="${firstId}"]`).click();
    await otherTab.locator('#toggleHintsBtn').click();
    const anotherTabExposure = await exported(otherTab);
    const previousEvents = new Set(importedEarly.hint_visibility.events.map(event => JSON.stringify(event)));
    assert(anotherTabExposure.hint_visibility.events.some(event => !previousEvents.has(JSON.stringify(event))));
    const importedAfterOtherTab = await importBackup(page, earlyV2, 'synthetic_early_v2_after_other_tab.json');
    assertHistoryRetained(anotherTabExposure, importedAfterOtherTab);
    assert.deepEqual(importedAfterOtherTab.annotations, legacy.annotations);
    await otherTab.close();
    await page.reload();
    const final = await exported(page);
    assert.deepEqual(final.annotations, legacy.annotations);
    assertHistoryRetained(importedAfterOtherTab, final);
    const csv = parseCsv(await downloaded(page, '#exportCsvBtn'));
    assert.equal(csv.rows.length, data.case_count);
    for (const row of csv.rows) {
      assert.equal(row.expert_id, 'expert_3');
      assert.equal(row.annotation_mode, 'method_assisted_review');
      assert.equal(row.hints_visible, 'false');
      assert.equal(row.hint_pack_hash, hints.pack_hash);
      assert.equal(row.hints_ever_shown, 'true');
      assert.deepEqual(sorted(JSON.parse(row.hints_shown_case_ids)), sorted(allSeen));
      assert.equal(row.case_hints_ever_shown, 'true');
      assert.equal(row.case_hints_currently_visible, 'false');
      assert.deepEqual(JSON.parse(row.hint_visibility_events), final.hint_visibility.events);
      assert.deepEqual(JSON.parse(row.case_hint_visibility_events), final.hint_visibility.events.filter(event => event.case_id === row.case_id));
    }
    assert.deepEqual(errors, []); assert.deepEqual(unexpectedRequests, []);
    const report = {passed:true, cases:5, sections:78, model_rows_checked:checkedRows,
      case_predictions_checked:checkedPredictions, prediction_public_fields_equal_parent:true,
      prediction_pack_has_no_private_answers_ids_or_paths:true, predictions_hidden_by_default:true,
      previous_v2_answers_and_old_pack_exposure_preserved:true,
      core_payload_and_storage_identity_unchanged:true, hints_equal_parent_sources:true,
      other_expert_answers_and_selection_metadata_absent:true, default_hints_not_in_dom:true,
      old_confirmed_and_draft_records_preserved_exactly:true, hint_actions_do_not_modify_answers_or_timestamps:true,
      exposure_history_retained_when_hidden_and_reloaded:true, open_reload_defaults_hidden:true,
      old_v1_import_cannot_erase_exposure:true, early_v2_import_cannot_erase_exposure:true,
      import_preserves_exposure_from_other_tab_storage:true,
      assisted_mode_persists_after_exposure:true, csv_exposure_history_exported:true, csv_rows:5, mobile_no_overflow:true,
      unexpected_network_requests:0, isolated_browser_storage_only:true};
    fs.writeFileSync(path.join(out, 'optional_hints_smoke_report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exit(1);});
