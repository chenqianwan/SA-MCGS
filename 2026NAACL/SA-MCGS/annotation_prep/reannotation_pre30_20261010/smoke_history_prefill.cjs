'use strict';
// Disposable browser contexts only: never accesses the user's annotation storage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = __dirname;
const out = path.join(root, 'qa');
const data = JSON.parse(fs.readFileSync(path.join(root, 'payload.json'), 'utf8'));
const currentHtml = fs.readFileSync(path.join(root, 'dist/pre30_reannotation.html'), 'utf8');
const previousHtml = fs.readFileSync(path.join(root, 'qa/history_prefill_before/dist/pre30_reannotation.html'), 'utf8');
const history = data.historical_annotations;
const origin = 'http://history-prefill.test';
const url = `${origin}/pre30_reannotation.html`;
const baseKey = `sa_mcgs_pre30_reannotation_v1:${data.study_id}:${data.manifest_hash}:${data.prediction_pack_hash}`;
const storageKey = slot => `${baseKey}:${slot}`;
const clone = value => JSON.parse(JSON.stringify(value));
const selected = (record, field) => Object.keys(record.sections).filter(id => record.sections[id][field]).sort();

async function downloaded(page, selector) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
  return fs.readFileSync(await download.path(), 'utf8');
}
const exported = async page => JSON.parse(await downloaded(page, '#exportJsonBtn'));
const stored = page => page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));

// RFC 4180 parser; notes and embedded JSON can contain quotes or line breaks.
function parseCsv(text) {
  const rows = []; let row = [], field = '', quoted = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { field += '"'; i += 1; }
      else quoted = !quoted;
    } else if (char === ',' && !quoted) { row.push(field); field = ''; }
    else if ((char === '\r' || char === '\n') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += char;
  }
  assert.equal(quoted, false, 'CSV has balanced quotes');
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const columns = rows.shift();
  return {columns, rows:rows.map(values => {
    assert.equal(values.length, columns.length);
    return Object.fromEntries(columns.map((column, i) => [column, values[i]]));
  })};
}

function assertScope(backup) {
  assert.equal(backup.study_id, data.study_id);
  assert.equal(Object.keys(backup.case_catalog).length, 18);
  assert(Object.keys(backup.annotations).every(id => data.cases.some(item => item.id === id)));
  for (const item of data.cases) {
    assert.deepEqual(backup.case_catalog[item.id], {
      content_hash:item.content_hash,
      sections:item.sections.map(section => ({id:section.id, source_node_id:section.source_node_id})),
    });
    if (backup.annotations[item.id]) {
      assert.equal(backup.annotations[item.id].content_hash, item.content_hash);
      assert.deepEqual(Object.keys(backup.annotations[item.id].sections).sort(), item.sections.map(section => section.id).sort());
    }
  }
}

async function assertDisplayedAnswers(page, annotations) {
  for (const item of data.cases) {
    const expected = annotations[item.id];
    await page.locator(`[data-case="${item.id}"]`).click();
    const shown = await page.evaluate(() => ({
      target_conflict:document.querySelector('input[name="target_conflict"]:checked')?.value ?? null,
      judgment_sufficient:document.querySelector('input[name="judgment_sufficient"]:checked')?.value ?? null,
      confidence:document.querySelector('input[name="confidence"]:checked')?.value ?? null,
      notes:document.querySelector('#notesInput').value,
      minimum:Array.from(document.querySelectorAll('input[data-field="minimal_evidence"]:checked')).map(node => node.dataset.sectionId).sort(),
      repair:Array.from(document.querySelectorAll('input[data-field="repair_material"]:checked')).map(node => node.dataset.sectionId).sort(),
    }));
    assert.deepEqual(shown, {
      target_conflict:expected.target_conflict,
      judgment_sufficient:expected.judgment_sufficient,
      confidence:expected.confidence === null ? null : String(expected.confidence),
      notes:expected.notes,
      minimum:selected(expected, 'minimal_evidence'), repair:selected(expected, 'repair_material'),
    }, `Visible answers match historical source for ${item.id}`);
  }
}

async function main() {
  assert.equal(data.cases.length, 18);
  assert.equal(history.schema_version, 'pre18_historical_annotations.v1');
  assert(history.pack_hash);
  for (const expert of ['expert_1', 'expert_2']) {
    assert.equal(Object.keys(history.experts[expert].annotations).length, 18);
    assert(history.experts[expert].provenance);
    assert.equal(Object.keys(history.experts[expert].case_provenance).length, 18);
  }
  assert(!history.experts.expert_3, 'Do not invent a third expert historical full-batch vote');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.ANNOTATION_CHROMIUM_PATH});
  const errors = [], unexpectedRequests = [], contexts = [];
  async function harness(initialHtml) {
    let html = initialHtml;
    const context = await browser.newContext({viewport:{width:1600,height:1100}, reducedMotion:'reduce'});
    contexts.push(context);
    await context.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/')) return route.fulfill({contentType:'text/html', body:html});
      unexpectedRequests.push(route.request().url());
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('dialog', dialog => dialog.accept());
    return {context, page, setHtml:value => { html = value; }};
  }
  try {
    const fresh = await harness(currentHtml), page = fresh.page;
    await page.goto(url);
    await page.locator('#app').waitFor({state:'visible'});
    assert.equal(await page.locator('#fatalError').isVisible(), false);
    assert.equal(await page.locator('.case-item').count(), 18);
    assert.equal(await page.locator('#previewNotice').isVisible(), false);
    assert.match(await page.locator('body').innerText(), /沿用原标注|历史已完成/);
    await page.screenshot({path:path.join(out, 'history_prefill_desktop.png')});
    const freshExports = {};
    for (const expert of ['expert_1', 'expert_2']) {
      await page.locator('#expertSelect').selectOption(expert);
      const backup = await exported(page);
      assertScope(backup);
      assert.deepEqual(backup.annotations, history.experts[expert].annotations, `${expert}: exact historical annotations`);
      assert(backup.historical_import, `${expert}: history provenance is exported`);
      assert.deepEqual(backup.historical_import.original_annotations, history.experts[expert].annotations);
      freshExports[expert] = clone(backup);
      await assertDisplayedAnswers(page, history.experts[expert].annotations);
      const csv = parseCsv(await downloaded(page, '#exportCsvBtn'));
      assert.equal(csv.rows.length, 18);
      for (const name of ['minimal_evidence_source_nodes','repair_material_source_nodes','content_hash']) assert(csv.columns.includes(name));
      for (const name of ['historical_reused','historical_pack_hash','historical_source_provenance',
        'historical_case_provenance','historical_original_annotation','annotation_origin']) assert(csv.columns.includes(name));
      for (const row of csv.rows) {
        const item = data.cases.find(candidate => candidate.id === row.case_id);
        assert(item, 'CSV contains only main experiment cases');
        const answer = backup.annotations[item.id];
        assert.equal(row.expert_id, expert);
        assert.equal(row.content_hash, item.content_hash);
        assert.equal(row.historical_reused, 'true');
        assert.equal(row.historical_pack_hash, history.pack_hash);
        assert.equal(row.annotation_origin, 'historical_reused');
        assert.deepEqual(JSON.parse(row.historical_source_provenance), history.experts[expert].provenance);
        assert.deepEqual(JSON.parse(row.historical_case_provenance), history.experts[expert].case_provenance[item.id]);
        assert.deepEqual(JSON.parse(row.historical_original_annotation), history.experts[expert].annotations[item.id]);
        for (const [field, column] of [['minimal_evidence','minimal_evidence_source_nodes'],['repair_material','repair_material_source_nodes']]) {
          assert.deepEqual(JSON.parse(row[column]), item.sections.filter(section => answer.sections[section.id][field]).map(section => section.source_node_id));
        }
      }
    }
    await page.locator('#expertSelect').selectOption('expert_3');
    assert.deepEqual((await exported(page)).annotations, {});
    assert.equal(await page.locator('input:checked').count(), 0);

    // Local edits remain the whole-case source of truth on reload and import.
    await page.locator('#expertSelect').selectOption('expert_1');
    await page.locator('[data-case="PRE-02"]').click();
    await page.locator('#notesInput').fill('SYNTHETIC partial reannotation, keep my change "exactly"\n第二行');
    const edited = await exported(page);
    assert.equal(edited.annotations['PRE-02'].confirmed, false);
    assert(edited.historical_import);
    await page.reload();
    let after = await exported(page);
    assert.deepEqual(after.annotations, edited.annotations);
    assert.deepEqual(after.historical_import, edited.historical_import);
    await page.locator('#expertSelect').selectOption('expert_2');
    assert.deepEqual((await exported(page)).annotations, freshExports.expert_2.annotations);
    await page.locator('#expertSelect').selectOption('expert_1');
    await page.locator('#notesInput').fill('SYNTHETIC later draft to restore from backup');
    await page.locator('#importFile').setInputFiles({name:'synthetic_history_backup.json', mimeType:'application/json', buffer:Buffer.from(JSON.stringify(edited))});
    await page.waitForFunction(() => document.querySelector('#saveStatus').textContent.includes('备份已恢复'));
    after = await exported(page);
    assert.deepEqual(after.annotations, edited.annotations);
    assert.deepEqual(after.historical_import, edited.historical_import);

    // Upgrade a previous 18-case page with a user's unconfirmed partial answer.
    const upgrade = await harness(previousHtml), oldPage = upgrade.page;
    await oldPage.goto(url);
    await oldPage.locator('input[name="target_conflict"][value="absent"]').check();
    await oldPage.locator('input[name="judgment_sufficient"][value="insufficient"]').check();
    await oldPage.locator('input[name="confidence"][value="2"]').check();
    await oldPage.locator('#notesInput').fill('SYNTHETIC existing draft: preserve the entire record');
    const prior = await exported(oldPage), priorStorage = await stored(oldPage);
    assert.equal(prior.annotations['PRE-01'].confirmed, false);
    const oldRaw = priorStorage[storageKey('expert_1')];
    assert(oldRaw);
    upgrade.setHtml(currentHtml);
    await oldPage.reload();
    const merged = await exported(oldPage);
    const expected = clone(history.experts.expert_1.annotations);
    expected['PRE-01'] = prior.annotations['PRE-01'];
    assert.deepEqual(merged.annotations, expected);
    assert(merged.historical_import);
    assertScope(merged);
    const upgradedStorage = await stored(oldPage);
    assert(Object.entries(upgradedStorage).some(([key, value]) => key !== storageKey('expert_1') && value === oldRaw), 'Existing 18-case raw data has an independent exact backup before prefill');
    await oldPage.reload();
    assert.deepEqual((await exported(oldPage)).annotations, expected);

    // Invalid current storage is never silently replaced by historical answers.
    const damaged = await harness(currentHtml), damagedPage = damaged.page;
    const invalidRaw = '{"SYNTHETIC_DAMAGED_STORAGE":';
    await damaged.context.addInitScript(({key, value}) => localStorage.setItem(key, value), {key:storageKey('expert_1'), value:invalidRaw});
    await damagedPage.goto(url);
    assert.equal(await damagedPage.locator('#fatalError').isVisible(), false);
    assert.equal(await damagedPage.locator('#storageNotice').isVisible(), true);
    assert.equal(await damagedPage.locator('#confirmBtn').isDisabled(), true);
    assert.equal(await damagedPage.locator('#exportCsvBtn').isDisabled(), true);
    assert.equal((await stored(damagedPage))[storageKey('expert_1')], invalidRaw);
    assert.equal(await downloaded(damagedPage, '#exportJsonBtn'), invalidRaw);

    assert.deepEqual(errors, []);
    assert.deepEqual(unexpectedRequests, []);
    const report = {passed:true, cases:18, historical_experts:2, historical_records_checked:36,
      all_visible_judgments_and_section_sets_equal_sources:true, expert_3_starts_blank:true,
      history_label_not_new_confirmation:true, source_node_mapping_checked:true, csv_rows_per_expert:18,
      csv_history_source_and_original_votes_preserved:true,
      existing_draft_retained_exactly:true, missing_17_history_records_added:true, prior_storage_backed_up_exactly:true,
      edits_survive_reload:true, expert_isolation:true, json_roundtrip_preserves_history_provenance:true,
      damaged_storage_not_overwritten:true, unexpected_network_requests:0, isolated_browser_storage_only:true};
    fs.writeFileSync(path.join(out, 'history_prefill_smoke_report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exit(1); });
