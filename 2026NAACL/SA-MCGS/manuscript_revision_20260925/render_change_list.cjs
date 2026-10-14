const { chromium } = require('/Users/chenlong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:'/Users/chenlong/Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell'});
  const page = await browser.newPage({viewport:{width:1400,height:1100}});
  await page.goto('file://' + path.join(__dirname,'CHANGE_LIST_BLUE.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({path:path.join(__dirname,'output/pdf/CHANGE_LIST_BLUE.pdf'),format:'A4',printBackground:true,displayHeaderFooter:true,
    headerTemplate:'<span></span>',footerTemplate:'<div style="width:100%;font-family:Arial;font-size:9px;color:#737b85;text-align:center"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    margin:{top:'15mm',bottom:'16mm',left:'14mm',right:'14mm'}});
  console.log(JSON.stringify(await page.evaluate(() => ({tables:document.querySelectorAll('table').length,rows:document.querySelectorAll('tbody tr').length,blueSpans:document.querySelectorAll('span[style]').length,rawHtmlVisible:document.body.innerText.includes('<span')}))));
  await browser.close();
})().catch(err => {console.error(err);process.exit(1);});
