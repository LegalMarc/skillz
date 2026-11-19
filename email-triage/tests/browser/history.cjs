const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('file:'))network.push(r.url())});
  await page.goto('file://'+__dirname+'/history-fixture.html');
  if(await page.locator('#filter').inputValue()!=='Inbox')throw Error('Inbox is not default');
  await page.locator('#filter').selectOption('all');
  if(await page.locator('tr[data-item="M001"] .placement-verified').innerText()!=='Placement verified')throw Error('receipt-backed completed action did not verify exact placement');
  if(await page.locator('tr[data-item="M002"] .placement-unverified').innerText()!=='Placement not verified')throw Error('mismatched completion receipt was treated as placement evidence');
  if(!(await page.locator('#receipt').innerText()).includes('1 verified moves'))throw Error('run receipt count included a completion with a mismatched receipt');
  await page.locator('#history').click();
  const historyText=await page.locator('.history-run').first().innerText();
  if(!historyText.includes('1 verified moves · 0 verified retained items'))throw Error('receipt-backed completed move omitted from history counts');
  await page.getByRole('button',{name:'Request undo for M001',exact:true}).click();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:/Export 1 changed item/}).click();
  const file=await download;await file.saveAs(__dirname+'/history-undo-bundle.json');
  const bundle=JSON.parse(require('fs').readFileSync(__dirname+'/history-undo-bundle.json'));
  if(bundle.moves.length!==1||bundle.moves[0].snapshot_numeric_id!==7||bundle.moves[0].destination!=='inbox')throw Error('Undo request lost exact identity');
  await page.locator('#history').click();
  await page.locator('#filter').selectOption('needs-me');
  if(await page.locator('tr[data-item]').count()!==1||!await page.locator('.badge.task-waiting_vendor').count()||!await page.locator('.badge.readiness-awaiting_assessment').count())throw Error('Explicit stored task/readiness status missing from What needs me');
  await page.locator('#filter').selectOption('all');
  const gist=page.getByRole('textbox',{name:'Correction or comment for M001'});await gist.fill('Pending user comment must survive history filters');
  const summary=await page.locator('#summary').innerText();await page.locator('#history').click();
  if(await page.locator('.history-run').count()!==2)throw Error('History missing runs');
  if(await page.locator('.history-run').filter({hasText:'Not yet reviewed'}).count()!==1)throw Error('Acknowledgment invented');
  await page.locator('#history-from').fill('2026-11-16');await page.locator('#history-to').fill('2026-11-16');await page.locator('#history-load').click();
  if(await page.locator('.history-run').count()!==1 || !(await page.locator('.history-run').innerText()).includes('latest-run'))throw Error('Range did not filter runs');
  await page.locator('#history-from').fill('2026-11-17');await page.locator('#history-load').click();if(!(await page.locator('#history-status').innerText()).includes('start date'))throw Error('Invalid range silently accepted');
  await page.locator('#history-from').fill('');await page.locator('#history-to').fill('');await page.locator('#history-load').click();
  if(await page.locator('img').count())throw Error('Historic email text became active HTML');
  await page.locator('#history').click();if(await gist.inputValue()!=='Pending user comment must survive history filters'||await page.locator('#summary').innerText()!==summary)throw Error('History changed current review');
  if(network.length||errors.length)throw Error(JSON.stringify({network,errors}));
  console.log('PASS: Inbox default, date-range history, truthful acknowledgment, inert historical text, retained comments, zero network/errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
