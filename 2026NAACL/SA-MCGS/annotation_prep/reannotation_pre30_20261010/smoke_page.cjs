'use strict';
// Disposable offline browser context. All answers below are synthetic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = __dirname;
const out = path.join(root, 'qa');
fs.mkdirSync(out, {recursive:true});
const payload = JSON.parse(fs.readFileSync(path.join(root, 'payload.json')));
async function downloaded(page, id) {
  const [d] = await Promise.all([page.waitForEvent('download'), page.locator(id).click()]);
  return fs.readFileSync(await d.path());
}
async function main() {
  const browser = await chromium.launch({headless:true, executablePath:process.env.ANNOTATION_CHROMIUM_PATH});
  const context = await browser.newContext({offline:true, viewport:{width:1440,height:1040}, reducedMotion:'reduce'});
  const page = await context.newPage();
  const errors=[], requests=[], dialogs=[];
  page.on('pageerror', e=>errors.push(String(e)));
  page.on('request', r=>{if(/^https?:/.test(r.url())) requests.push(r.url());});
  page.on('dialog', async d=>{dialogs.push(d.message()); await d.accept();});
  const url = pathToFileURL(path.join(root, 'dist/pre30_reannotation.html')).href;
  const json = async()=>JSON.parse((await downloaded(page,'#exportJsonBtn')).toString());
  try {
    await page.goto(url);
    await page.locator('#app').waitFor({state:'visible'});
    assert.equal(await page.locator('#fatalError').isVisible(),false);
    assert.equal(await page.locator('.case-item').count(),payload.cases.length);
    assert.equal(await page.locator('#previewNotice').isVisible(),false);
    assert.equal(await page.locator('#progressBar').getAttribute('max'),String(payload.cases.length));
    assert.deepEqual((await json()).annotations,payload.historical_annotations.experts.expert_1.annotations);
    await page.locator('#expertSelect').selectOption('expert_3');
    assert.equal(await page.locator('input:checked').count(),0);
    assert.deepEqual((await json()).annotations,{});
    await page.screenshot({path:path.join(out,'desktop_initial.png')});
    // Every displayed prediction must agree with its exact source record.
    for(const item of payload.cases) {
      await page.locator(`[data-case="${item.id}"]`).click();
      const cards=page.locator('.prediction-card');
      assert.equal(await cards.count(),payload.models.length);
      for(let i=0;i<payload.models.length;i++) {
        const p=item.sa_predictions.find(p=>p.model===payload.models[i].id);
        const expected=p.status==='pending'?'待运行':p.status==='invalid'?'无有效结果':p.risk_found?'有风险':'未判风险';
        assert.equal(await cards.nth(i).locator('.prediction-status').innerText(),expected);
      }
      assert.equal(await page.locator('.material-section').count(),item.sections.length);
    }
    await page.locator('[data-case="PRE-01"]').click();
    await page.locator('input[name=target_conflict][value=present]').check();
    await page.locator('input[name=judgment_sufficient][value=sufficient]').check();
    await page.locator('input[name=confidence][value="4"]').check();
    await page.locator('#confirmBtn').click();
    assert.match(await page.locator('#validationMessage').innerText(),/最小证据/);
    await page.locator('input[data-section-id=S001][data-field=minimal_evidence]').check();
    assert.equal(await page.locator('input[data-section-id=S001][data-field=repair_material]').isChecked(),true);
    await page.locator('#confirmBtn').click();
    let backup=await json();
    assert.equal(backup.annotations['PRE-01'].confirmed,true);
    assert.equal(backup.sa_visible,true);
    assert.equal(backup.annotation_mode,'method_assisted_reannotation');
    await page.locator('#notesInput').fill('TEST ONLY: comma, quote " and newline\n第二行');
    assert.equal((await json()).annotations['PRE-01'].confirmed,false);
    await page.locator('#confirmBtn').click();
    backup=await json();
    await page.reload();
    await page.locator('#expertSelect').selectOption('expert_3');
    assert.equal((await json()).annotations['PRE-01'].confirmed,true);
    await page.locator('#expertSelect').selectOption('expert_2');
    assert.deepEqual((await json()).annotations,payload.historical_annotations.experts.expert_2.annotations);
    await page.locator('#expertSelect').selectOption('expert_3');
    assert.equal((await json()).annotations['PRE-01'].confirmed,true);
    await page.locator('[data-case="PRE-02"]').click();
    await page.locator('input[name=target_conflict][value=absent]').check();
    await page.locator('input[name=judgment_sufficient][value=insufficient]').check();
    await page.locator('input[name=confidence][value="2"]').check();
    await page.locator('#confirmBtn').click();
    const second=(await json()).annotations['PRE-02'];
    assert.equal(second.target_conflict,'absent');
    assert.equal(second.judgment_sufficient,'insufficient');
    fs.writeFileSync(path.join(out,'synthetic_export.csv'),await downloaded(page,'#exportCsvBtn'));
    // Strict same-batch restore, with user-visible confirmation.
    await page.locator('#importFile').setInputFiles({name:'synthetic_backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});
    await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent.includes('备份已恢复'));
    assert.deepEqual((await json()).annotations,backup.annotations);
    const bad={...backup,study_id:'old_batch'};
    await page.locator('#importFile').setInputFiles({name:'wrong_batch.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
    await page.waitForTimeout(150);
    assert(dialogs.some(x=>x.includes('导入失败')));
    assert.deepEqual((await json()).annotations,backup.annotations);
    await page.locator('#expertSelect').selectOption('expert_3');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'mobile_initial.png')});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
    assert.deepEqual(errors,[]); assert.deepEqual(requests,[]);
    const result={passed:true,cases:payload.cases.length,prediction_cards_checked:payload.cases.length*payload.models.length,third_expert_blank_initial:true,
      save_reload:true,expert_isolation:true,confirmation_invalidation:true,strict_backup_roundtrip:true,
      wrong_batch_rejected:true,no_network_requests:true,mobile_no_horizontal_overflow:true,synthetic_edits_only:true};
    fs.writeFileSync(path.join(out,'smoke_report.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exit(1);});
