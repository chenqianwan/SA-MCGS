const { chromium } = require('/Users/chenlong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Users/chenlong/Library/Caches/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-mac-arm64/chrome-headless-shell'});
  const page = await browser.newPage({viewport:{width:1440,height:1100}, deviceScaleFactor:1});
  await page.goto('file://' + path.join(__dirname, 'MASTER_REVISION_PLAN_BLUE.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path:path.join(__dirname, 'output/pdf/MASTER_REVISION_PLAN_BLUE.pdf'),
    format:'A4', printBackground:true, displayHeaderFooter:true,
    headerTemplate:'<span></span>',
    footerTemplate:'<div style="width:100%;font-family:Arial;font-size:9px;color:#737b85;text-align:center"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    margin:{top:'17mm',bottom:'18mm',left:'16mm',right:'16mm'}
  });
  await page.screenshot({path:path.join(__dirname,'blue_preview_top.png')});
  console.log(JSON.stringify(await page.evaluate(() => ({
    tables:document.querySelectorAll('table').length,
    headings:document.querySelectorAll('h2').length,
    blueSpans:document.querySelectorAll('span[style]').length,
    rawHtmlVisible:document.body.innerText.includes('<span'),
    bodyWidth:document.body.scrollWidth,
    viewport:window.innerWidth
  }))));
  await browser.close();
})().catch(err => {console.error(err);process.exit(1);});
