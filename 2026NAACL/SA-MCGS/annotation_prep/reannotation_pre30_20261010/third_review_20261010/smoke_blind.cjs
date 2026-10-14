'use strict';
// Tests run only in disposable browsers against an intercepted local HTML response.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = __dirname, parent = path.dirname(root), out = path.join(root, 'qa');
const data = JSON.parse(fs.readFileSync(path.join(root, 'payload.json'), 'utf8'));
const html = fs.readFileSync(path.join(parent, 'dist/expert3_blind_20261010.html'), 'utf8');
const url = 'http://blind-expert3.test/expert3_blind_20261010.html';
const clone = value => JSON.parse(JSON.stringify(value));
const normalized = value => String(value).replace(/\s+/g, ' ').trim();

function keysOnly(value, allowed, label) {
  assert(value && typeof value === 'object' && !Array.isArray(value), `${label} is an object`);
  assert.deepEqual(Object.keys(value).sort(), [...allowed].sort(), `${label} has only the public fields`);
}
function validatePublicPayload(payload) {
  keysOnly(payload, ['schema_version','study_id','manifest_hash','annotation_protocol','annotation_mode',
    'expert_id','hints_visible','case_count','cases'], 'payload');
  assert.equal(payload.schema_version, 'third_expert_blind_payload.v1');
  assert.equal(payload.study_id, 'expert3_blind_20261010');
  assert.equal(payload.annotation_protocol, 'binary_judgment_v1');
  assert.equal(payload.annotation_mode, 'blind');
  assert.equal(payload.expert_id, 'expert_3');
  assert.equal(payload.hints_visible, false);
  assert.match(payload.manifest_hash, /^(sha256:)?[a-f0-9]{64}$/);
  assert.equal(payload.case_count, payload.cases.length);
  assert(payload.case_count > 0 && payload.case_count <= 18);
  payload.cases.forEach((item, index) => {
    keysOnly(item, ['id','order','content_hash','sections'], `case ${index}`);
    assert.equal(item.id, `B-${String(index + 1).padStart(2, '0')}`);
    assert.equal(item.order, index + 1);
    assert.match(item.content_hash, /^(sha256:)?[a-f0-9]{64}$/);
    assert(item.sections.length > 0);
    item.sections.forEach((section, position) => {
      keysOnly(section, ['id','heading','original_text','zh_heading','zh_text'], `section ${item.id}/${position}`);
      assert.equal(section.id, `S${String(position + 1).padStart(3, '0')}`);
      assert.equal(typeof section.heading, 'string');
      assert.equal(typeof section.original_text, 'string');
      assert(section.original_text.trim().length > 0);
      for (const field of ['zh_heading', 'zh_text']) assert(section[field] === null || typeof section[field] === 'string');
    });
  });
}
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
async function downloaded(page, selector) {
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selector).click()]);
  return fs.readFileSync(await download.path(), 'utf8');
}
const exported = async page => JSON.parse(await downloaded(page, '#exportJsonBtn'));
const stored = page => page.evaluate(() => Object.fromEntries(Object.entries(localStorage)));

async function main() {
  validatePublicPayload(data);
  // Private build audit: independently enforce the user's narrowed selection rule.
  // None of these identifiers or votes are copied into browser fixtures or outputs.
  const audit = JSON.parse(fs.readFileSync(path.join(root, 'internal/selection_audit.json'), 'utf8'));
  assert.equal(audit.decisions.length, 18);
  const selectedIds = audit.decisions.filter(decision => {
    const first = decision.expert_1, second = decision.expert_2;
    const qualifies = first.confidence < 3 || second.confidence < 3
      || first.target_conflict !== second.target_conflict;
    assert.equal(decision.selected, qualifies, 'Selection is only confidence below 3 or different conflict judgments');
    return qualifies;
  }).map(decision => decision.case_id).sort();
  assert.deepEqual(Object.values(audit.blind_mapping).map(item => item.case_id).sort(), selectedIds);
  assert.deepEqual(Object.keys(audit.blind_mapping).sort(), data.cases.map(item => item.id).sort());
  assert.equal(data.case_count, selectedIds.length);
  // Check executable and inert source too, not just hidden/visible DOM elements.
  for (const pattern of [/PRE-\d{2}/, /expert_[12]\b/, /historical_annotations/, /historical_import/,
    /SA-MCGS/, /node_results/, /sa_predictions/, /prediction_pack_hash/, /\bmodels\s*:/,
    /risk_found/, /source_presentation_id/, /selection_reason/, /original_ratings/]) {
    assert(!pattern.test(html), `Public HTML leaks forbidden information: ${pattern}`);
  }
  assert.equal(fs.readFileSync(path.join(parent, 'dist/pre30_reannotation.html'), 'utf8'), html,
    'Legacy public URL serves the same blind-only page');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true, executablePath:process.env.ANNOTATION_CHROMIUM_PATH});
  const errors = [], requests = [], dialogs = [], contexts = [];
  async function harness() {
    const context = await browser.newContext({viewport:{width:1440,height:1040}, reducedMotion:'reduce'});
    contexts.push(context);
    await context.route('**/*', route => {
      if (route.request().url() === url && route.request().resourceType() === 'document') {
        return route.fulfill({contentType:'text/html', body:html});
      }
      requests.push(route.request().url());
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(String(error)));
    page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.accept(); });
    return {context, page};
  }
  try {
    const fresh = await harness(), page = fresh.page;
    const oldPayload = JSON.parse(fs.readFileSync(path.join(parent, 'payload.json'), 'utf8'));
    const oldKeys = [];
    for (const identity of [oldPayload, oldPayload.predecessor].filter(Boolean)) {
      for (const slot of ['expert_1','expert_2','expert_3']) {
        oldKeys.push(`sa_mcgs_pre30_reannotation_v1:${identity.study_id}:${identity.manifest_hash}:${identity.prediction_pack_hash}:${slot}`);
      }
    }
    oldKeys.push('sa_mcgs_expert3_annotation_v1:prior_batch:expert_3');
    const oldRaw = JSON.stringify({private_old_answer:'SYNTHETIC_DO_NOT_MIGRATE', target_conflict:'present', expert_id:'expert_1'});
    await fresh.context.addInitScript(({keys, raw}) => {
      for (const key of keys) localStorage.setItem(key, raw);
      window.__qaStorageReads = [];
      const original = Storage.prototype.getItem;
      Storage.prototype.getItem = function(key) {
        window.__qaStorageReads.push(String(key)); return original.call(this, key);
      };
    }, {keys:oldKeys, raw:oldRaw});
    await page.goto(url);
    await page.locator('#app').waitFor({state:'visible'});
    assert.equal(await page.locator('#fatalError').isVisible(), false);
    assert.equal(await page.locator('[data-case]').count(), data.case_count);
    assert.equal(await page.locator('input:checked').count(), 0);
    assert.equal(await page.locator('.prediction-card,.node-hints,.method-hints,[data-model],[data-method]').count(), 0);
    assert.equal(await page.locator('option[value="expert_1"],option[value="expert_2"]').count(), 0);
    assert.equal(await page.locator('input[type="checkbox"]:not([data-section-id])').count(), 0,
      'No hint toggle is available');
    const embedded = await page.locator('#payloadData').textContent();
    assert.deepEqual(JSON.parse(embedded), data);
    const initial = await exported(page);
    assert.equal(initial.schema_version, 'third_expert_blind.export.v1');
    assert.equal(initial.annotation_mode, 'blind');
    assert.equal(initial.expert_id, 'expert_3');
    assert.equal(initial.hints_visible, false);
    assert(initial.sa_visible === undefined || initial.sa_visible === false);
    assert.deepEqual(initial.annotations, {});
    assert.equal(Object.keys(initial.case_catalog).length, data.case_count);
    assert(!JSON.stringify(initial).includes('SYNTHETIC_DO_NOT_MIGRATE'));
    await page.screenshot({path:path.join(out, 'blind_desktop.png')});
    const checkedSections = data.cases.reduce((sum, item) => sum + item.sections.length, 0);
    if (await page.locator('#languageSelect').count()) await page.locator('#languageSelect').selectOption('original');
    for (const item of data.cases) {
      await page.locator(`[data-case="${item.id}"]`).click();
      assert.equal(await page.locator('.material-section').count(), item.sections.length);
      for (const section of item.sections) {
        const node = page.locator(`.material-section[data-section="${section.id}"]`);
        assert.equal(await node.count(), 1);
        assert(normalized(await node.textContent()).includes(normalized(section.original_text)),
          `Complete original text rendered: ${item.id}/${section.id}`);
      }
    }
    if (await page.locator('#languageSelect').count()) await page.locator('#languageSelect').selectOption('zh');
    const firstId = data.cases[0].id;
    await page.locator(`[data-case="${firstId}"]`).click();
    await page.locator('input[name="target_conflict"][value="present"]').check();
    await page.locator('input[name="judgment_sufficient"][value="sufficient"]').check();
    await page.locator('input[name="confidence"][value="4"]').check();
    await page.locator('#confirmBtn').click();
    assert.match(await page.locator('#validationMessage').innerText(), /最小证据/);
    assert.equal((await exported(page)).annotations[firstId].confirmed, false);
    await page.locator('input[data-section-id="S001"][data-field="minimal_evidence"]').check();
    assert.equal(await page.locator('input[data-section-id="S001"][data-field="repair_material"]').isChecked(), true);
    await page.locator('#confirmBtn').click();
    let backup = await exported(page);
    assert.equal(backup.annotations[firstId].confirmed, true);
    await page.locator('#notesInput').fill('SYNTHETIC blind test: comma, quote " and newline\n第二行');
    assert.equal((await exported(page)).annotations[firstId].confirmed, false);
    await page.locator('#confirmBtn').click();
    backup = await exported(page);
    await page.reload();
    assert.deepEqual((await exported(page)).annotations, backup.annotations);
    const storage = await stored(page);
    const newKeys = Object.keys(storage).filter(key => !oldKeys.includes(key));
    assert.equal(newKeys.length, 1, 'Blind page uses a single independent active storage key');
    const activeKey = newKeys[0];
    assert.equal(activeKey, `third_expert_blind_v1:${data.study_id}:${data.manifest_hash}:expert_3`);
    for (const key of oldKeys) assert.equal(storage[key], oldRaw, 'Old stored annotations are untouched');
    const reads = await page.evaluate(() => window.__qaStorageReads);
    assert(reads.length > 0);
    assert(reads.every(key => !oldKeys.includes(key)), 'Blind page never even reads old annotations');
    const csv = parseCsv(await downloaded(page, '#exportCsvBtn'));
    assert.equal(csv.rows.length, data.case_count);
    for (const row of csv.rows) {
      assert(data.cases.some(item => item.id === row.case_id));
      assert.equal(row.expert_id, 'expert_3');
      assert.equal(row.annotation_mode, 'blind');
      assert.equal(row.hints_visible, 'false');
    }
    for (const column of csv.columns) assert(!/historical|prediction|model|source_node|source_presentation/.test(column));
    await page.locator('#notesInput').fill('SYNTHETIC draft replaced by exported backup');
    await page.locator('#importFile').setInputFiles({name:'synthetic_blind_backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});
    await page.waitForFunction(() => document.querySelector('#saveStatus').textContent.includes('备份已恢复'));
    assert.deepEqual((await exported(page)).annotations, backup.annotations);
    const wrong = {...clone(backup), study_id:'prior_nonblind_batch'};
    await page.locator('#importFile').setInputFiles({name:'wrong_batch.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(wrong))});
    await page.waitForTimeout(100);
    assert(dialogs.some(text => text.includes('导入失败')));
    assert.deepEqual((await exported(page)).annotations, backup.annotations);

    // A clean mobile context displays no synthetic answers in the screenshot.
    const mobile = await harness();
    await mobile.page.setViewportSize({width:390,height:844});
    await mobile.page.goto(url);
    await mobile.page.screenshot({path:path.join(out, 'blind_mobile.png')});
    assert(await mobile.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));

    // Corruption protection must export the original bytes and avoid replacement.
    const damaged = await harness(), invalidRaw = '{"SYNTHETIC_CORRUPT":';
    await damaged.context.addInitScript(({key, raw}) => localStorage.setItem(key, raw), {key:activeKey, raw:invalidRaw});
    await damaged.page.goto(url);
    assert.equal(await damaged.page.locator('#storageNotice').isVisible(), true);
    assert.equal(await damaged.page.locator('#confirmBtn').isDisabled(), true);
    assert.equal(await damaged.page.locator('#exportCsvBtn').isDisabled(), true);
    assert.equal((await stored(damaged.page))[activeKey], invalidRaw);
    assert.equal(await downloaded(damaged.page, '#exportJsonBtn'), invalidRaw);
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    const report = {passed:true, cases:data.case_count, complete_original_sections_checked:checkedSections,
      selected_only_confidence_below_3_or_conflict_disagreement:true,
      public_payload_recursive_allowlist:true, public_html_no_private_results:true, legacy_url_blind_only:true,
      empty_initial_answers:true, only_expert_3:true, no_hints_or_hint_toggle:true, old_storage_not_read_or_changed:true,
      minimum_evidence_validation:true, minimum_implies_repair:true, confirmation_invalidated_on_change:true,
      save_reload:true, same_batch_json_roundtrip:true, wrong_batch_rejected:true, csv_rows:data.case_count,
      mobile_no_overflow:true, damaged_storage_not_overwritten:true, unexpected_network_requests:0,
      isolated_browser_storage_only:true};
    fs.writeFileSync(path.join(out, 'blind_smoke_report.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report, null, 2));
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}
main().catch(error => {console.error(error); process.exit(1);});
