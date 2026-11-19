const {chromium}=require('playwright');
const {pathToFileURL}=require('url');
const path=require('path');
const fs=require('fs');
const {randomUUID}=require('crypto');
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(path.resolve(process.argv[2]||path.join(__dirname,'fixture.html'))).href);
    if(await page.locator('#filter').inputValue()!=='Inbox')throw Error('Default is not current Inbox');
    await page.locator('#filter').selectOption('all');
    if(!process.argv[2]) {
      const order=()=>page.locator('tr[data-item]').evaluateAll(rows=>rows.map(r=>r.dataset.item));
      await page.locator('button[data-sort=size_bytes]').click();
      if(JSON.stringify(await order())!==JSON.stringify(['M001','M003','M002']))throw Error('Size is not numeric ascending with unknown last');
      await page.locator('button[data-sort=size_bytes]').click();
      if(JSON.stringify(await order())!==JSON.stringify(['M003','M001','M002']))throw Error('Size is not numeric descending with unknown last');
      await page.getByRole('textbox',{name:'Correction or comment for M001'}).fill('Responsive edit retained across viewport changes');
      await page.getByRole('button',{name:'Opt Out M001',exact:true}).click();
    }
    await page.evaluate(()=>{
      const section=document.createElement('section');section.className='pending-review-preserved';section.setAttribute('aria-label','Preserved pending review selection');
      const paragraph=document.createElement('p');paragraph.textContent='pendingusertext'.repeat(40);section.append(paragraph);document.body.prepend(section);
    });
    for(const width of [1920,1440,1280,1200,1199,1024,768,500,375,320]) {
      await page.setViewportSize({width,height:1000});
      const overflow=await page.evaluate(()=>{
        const viewport=document.documentElement.clientWidth;
        return [...document.querySelectorAll('body,main,.pending-review-preserved,.toolbar,.table-wrap,table,thead,tbody,tr,td,button,input,select,textarea')].filter(e=>{
          if(!e.getClientRects().length)return false;
          const box=e.getBoundingClientRect();return box.left < -1 || box.right > viewport+1;
        }).slice(0,8).map(e=>e.tagName+'.'+e.className);
      });
      const scroll=await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth+1 || document.querySelector('.table-wrap').scrollWidth>document.querySelector('.table-wrap').clientWidth+1);
      if(overflow.length||scroll)throw Error(`Horizontal overflow at ${width}: ${overflow}`);
      if(await page.locator('.pending-review-preserved').evaluate(section=>section.scrollWidth>section.clientWidth+1))throw Error(`Pending selection text overflows at ${width}`);
      if(width<=1199 && await page.locator('tr[data-item]').first().locator('td[data-label]').count()!==9)throw Error('Card labels missing');
      for(const action of ['Opt Out','Move to Inbox','Archive']){
        const button=page.locator('tr[data-item]').first().getByRole('button',{name:new RegExp('^'+action+' M')});
        if(!await button.isVisible())throw Error('Responsive action hidden: '+action);
      }
      if((width===1440||width===375) && (!process.argv[2] || process.argv[3])){
        const directory=process.argv[3]||__dirname;fs.mkdirSync(directory,{recursive:true,mode:0o700});
        const target=path.join(directory,`responsive-${width}.png`),temporary=path.join(directory,`.screenshot-${randomUUID()}`);
        fs.writeFileSync(temporary,await page.screenshot(),{mode:0o600,flag:'wx'});fs.renameSync(temporary,target);
      }
      if(await page.getByRole('columnheader').count()!==9 || !await page.locator('tr[data-item]').first().getByRole('cell').count())throw Error('Accessible table structure lost');
    }
    if(!process.argv[2] && await page.getByRole('textbox',{name:'Correction or comment for M001'}).inputValue()!=='Responsive edit retained across viewport changes')throw Error('Resize lost edits');
    if(errors.length)throw Error(errors.join('\n'));
    console.log('PASS: independent numeric Size sort, unknown last, 320–1920px without horizontal overflow including long pending text, visible controls, labeled cards and retained edits');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
