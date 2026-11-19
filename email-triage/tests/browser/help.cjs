const {chromium}=require('playwright');
const {pathToFileURL}=require('url');
const path=require('path');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve(process.argv[2]||path.join(__dirname,'fixture.html'))).href);
  await page.locator('#filter').selectOption('all');
  const summary=await page.locator('#summary').textContent();
  if(!/Last Refreshed: \d{2}\.\d{2}\.\d{2} @ \d{1,2}(?::\d{2})?(?:am|pm) [A-Z]+/.test(summary))throw Error('Missing formatted refresh stamp');
  if(await page.locator('#scope,#refresh-note,caption').count())throw Error('Verbose main-view elements remain');
  if(!(await page.locator('header').innerText()).includes('EMAIL TRIAGE · LOCAL REVIEW') || !(await page.locator('#execution').innerText()).length)throw Error('Missing accurate LLM provenance header');
  const gist=page.locator('tr[data-item] textarea').first(),original=await gist.inputValue();
  if(!process.argv[2])await gist.fill('Keep this pending edit while Help is open');
  for(const width of [1440,375,320]) {
   await page.setViewportSize({width,height:900});
   await page.getByRole('button',{name:'Help',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'Using email review'});
   if(!await dialog.isVisible())throw Error('Help did not open');
   const backgroundScroll=await page.evaluate(()=>scrollY);await page.mouse.move(2,2);await page.mouse.wheel(0,500);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));if(await page.evaluate(()=>scrollY)!==backgroundScroll)throw Error('Backdrop scrolled background');
   if(!await page.getByRole('button',{name:'Close Help',exact:true}).evaluate(e=>e===document.activeElement))throw Error('Initial focus not on Close Help');
   await page.keyboard.press('Shift+Tab');
   if(!await page.locator('#help-dialog').evaluate(d=>d.contains(document.activeElement)))throw Error('Keyboard focus escaped Help');
   const bounds=await page.locator('#help-body').evaluate(e=>({scroll:e.scrollHeight>e.clientHeight,bottom:e.getBoundingClientRect().bottom,dialogBottom:e.closest('dialog').getBoundingClientRect().bottom,width:document.documentElement.scrollWidth,viewport:document.documentElement.clientWidth}));
   if(!bounds.scroll||bounds.bottom>bounds.dialogBottom+1||bounds.width>bounds.viewport+1)throw Error('Help not independently scrollable/fitted at '+width);
   await page.locator('#help-body').focus();await page.keyboard.press('PageDown');await page.waitForFunction(()=>document.getElementById('help-body').scrollTop>0);
   for(const title of ['Overview','Review and apply changes','Row controls','Assign a follow-up task','Save, resume and refresh','Dates, sizes and this report','Safety and troubleshooting'])if(await dialog.getByRole('heading',{name:title,exact:true}).count()!==1)throw Error('Missing help section '+title);
   const helpText=await page.locator('#help-body').innerText();if(helpText.includes('Normal triage actions have already been executed and verified')||helpText.includes('This run’s completed moves remain available'))throw Error('Help made an unconditional verified-action claim');
   if(await page.locator('#help-refreshed').textContent()!==summary.split('Last Refreshed: ')[1])throw Error('Help time differs from count line');
   await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.documentElement.classList.contains('help-open'));
   if(await dialog.isVisible()||!await page.getByRole('button',{name:'Help',exact:true}).evaluate(e=>e===document.activeElement))throw Error('Escape/focus restoration failed');
   await page.getByRole('button',{name:'Help',exact:true}).click();
   if(await page.locator('#help-body').evaluate(e=>e.scrollTop)!==0)throw Error('Help did not reopen at overview');
   await page.getByRole('button',{name:'Close Help',exact:true}).click();
   await page.getByRole('button',{name:'Help',exact:true}).click();await page.mouse.click(2,2);
   if(await dialog.isVisible())throw Error('Backdrop did not close Help');
  }
  if(await gist.inputValue()!==(!process.argv[2]?'Keep this pending edit while Help is open':original))throw Error('Help changed pending edits');
  if(await page.locator('#summary').textContent()!==summary)throw Error('Help changed timestamp/counts');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: compact main view, refresh stamp, Help sections, scroll, focus, Escape/Close/backdrop, 320–1440px, unchanged edits/counts');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
