'use strict';
// Isolated context: preserve synthetic old-page progress across the page update.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = __dirname;
const data = JSON.parse(fs.readFileSync(path.join(root, 'payload.json')));
async function main() {
  const browser = await chromium.launch({headless:true, executablePath:process.env.ANNOTATION_CHROMIUM_PATH});
  const context = await browser.newContext({viewport:{width:1600,height:1100}, reducedMotion:'reduce'});
  const page = await context.newPage(), errors=[];
  page.on('pageerror', e=>errors.push(String(e)));
  let html = fs.readFileSync(path.join(root,'qa/main18_scope_before/dist/pre30_reannotation.html'),'utf8');
  await context.route('http://pre30.test/**', route=>route.fulfill({contentType:'text/html',body:html}));
  const exported = async()=>{
    const [d]=await Promise.all([page.waitForEvent('download'),page.locator('#exportJsonBtn').click()]);
    return JSON.parse(fs.readFileSync(await d.path(),'utf8'));
  };
  try {
    await page.goto('http://pre30.test/pre30_reannotation.html');
    await page.locator('input[name=target_conflict][value=absent]').check();
    await page.locator('input[name=judgment_sufficient][value=sufficient]').check();
    await page.locator('input[name=confidence][value="4"]').check();
    await page.locator('#notesInput').fill('SYNTHETIC OLD PAGE: preserve this answer');
    await page.locator('#confirmBtn').click();
    await page.locator('[data-case="PRE-19"]').click();
    await page.locator('input[name=target_conflict][value=absent]').check();
    await page.locator('input[name=judgment_sufficient][value=sufficient]').check();
    await page.locator('input[name=confidence][value="3"]').check();
    await page.locator('#notesInput').fill('SYNTHETIC EXCLUDED CASE: retain only in the original backup');
    await page.locator('#confirmBtn').click();
    const before=await exported();
    assert(before.annotations['PRE-01'].confirmed);
    assert(before.annotations['PRE-19'].confirmed);
    const priorStorage=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));
    html=fs.readFileSync(path.join(root,'dist/pre30_reannotation.html'),'utf8');
    await page.reload();
    const after=await exported();
    const expected={...data.historical_annotations.experts.expert_1.annotations,'PRE-01':before.annotations['PRE-01']};
    assert.deepEqual(after.annotations,expected);
    assert.equal(after.active_case_id,'PRE-01');
    assert.equal(Object.keys(after.case_catalog).length,18);
    assert.equal(await page.locator('.case-item').count(),18);
    assert.equal(await page.locator('[data-case="PRE-19"]').count(),0);
    assert.equal(await page.locator('#previewNotice').isVisible(),false);
    const nextStorage=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));
    for(const [key,value] of Object.entries(priorStorage))assert.equal(nextStorage[key],value,'Original 30-case storage must be retained');
    assert.deepEqual(after.method_hints_visible,['sa-mcgs','lea']);
    assert.equal(after.node_results_pack_hash,data.node_results_pack_hash);
    assert.deepEqual(after.node_results,data.node_results);
    page.on('dialog',async d=>d.accept());
    await page.locator('#importFile').setInputFiles({name:'previous_scope.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(before))});
    await page.waitForFunction(()=>document.querySelector('#saveStatus').textContent.includes('备份已恢复'));
    assert.deepEqual((await exported()).annotations,expected);
    await page.reload();
    assert.deepEqual((await exported()).annotations,expected);
    let checked=0;
    for (const item of data.cases) {
      await page.locator(`[data-case="${item.id}"]`).click();
      const rendered=await page.locator('.material-section').evaluateAll(sections=>sections.map(section=>({
        id:section.dataset.section,
        hints:Array.from(section.querySelectorAll('.model-hint')).map(node=>({
          method:node.closest('[data-method]').dataset.method,model:node.dataset.model,text:node.innerText,
          unavailable:node.classList.contains('unavailable')}))
      })));
      assert.equal(rendered.length,item.sections.length);
      for(const section of rendered) {
        assert.equal(section.hints.length,4);
        for(const node of section.hints) {
          const h=data.node_results[item.id][section.id].methods[node.method].models[node.model];
          if(h.status==='available') {
            assert(!node.unavailable);
            assert(node.text.includes(h.selected?'已纳入结果子图':'未纳入结果子图'));
            assert(node.text.includes(`风险相关分 ${h.score===null?'—':h.score.toFixed(3)}`));
            if(h.rank!==null)assert(node.text.includes(`第 ${h.rank} / ${h.total_nodes}`));
          } else {
            assert(node.unavailable);
            assert(!node.text.includes('未纳入结果子图'));
            assert(node.text.includes(h.status==='not_run'?'尚未运行':'无有效结果'));
          }
          checked++;
        }
      }
    }
    await page.locator('[data-case="PRE-01"]').click();
    await page.locator('.material-section').first().scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'qa/node_hints_desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await page.locator('.material-section').first().scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'qa/node_hints_mobile.png')});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);
    const report={passed:true,node_model_rows_checked:checked,old_progress_preserved:true,
      excluded_case_not_in_active_annotations:true,old_storage_untouched:true,old_30_backup_imported:true,
      hint_snapshot_exported:true,unavailable_not_negative:true,mobile_no_overflow:true,synthetic_edits_only:true};
    fs.writeFileSync(path.join(root,'qa/node_hints_smoke_report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e);process.exit(1);});
