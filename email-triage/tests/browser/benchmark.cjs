const {chromium}=require('playwright');
const {pathToFileURL}=require('url');
const path=require('path');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const sizes=process.argv.slice(2).map(Number);const requested=sizes.length?sizes:[100,1000,10000];
  for(const size of requested){
   if(![100,1000,10000].includes(size))throw Error('Supported synthetic sizes: 100, 1000, 10000');
   const page=await browser.newPage();await page.goto(pathToFileURL(path.join(__dirname,`benchmark-${size}.html`)).href);
   const result=await page.evaluate(async(size)=>{
    const start=performance.now();document.querySelector('#filter').dispatchEvent(new Event('change',{bubbles:true}));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const inboxMs=performance.now()-start,visible=document.querySelectorAll('tr[data-item]').length;
    const field=document.querySelector('tr[data-item] td.gist textarea');field.focus();const editStart=performance.now();field.value='Benchmark correction';field.dispatchEvent(new Event('input',{bubbles:true}));
    const editMs=performance.now()-editStart,focusRetained=document.activeElement===field;
    const searchStart=performance.now(),search=document.querySelector('#search');search.value=`Synthetic message ${size}`;search.dispatchEvent(new Event('input',{bubbles:true}));
    await new Promise(resolve=>setTimeout(resolve,180));
    return {records:size,inbox_visible:visible,search_matches:document.querySelectorAll('tr[data-item]').length,inbox_filter_ms:Number(inboxMs.toFixed(2)),edit_event_ms:Number(editMs.toFixed(2)),search_elapsed_including_debounce_ms:Number((performance.now()-searchStart).toFixed(2)),focus_retained:focusRetained};
   },size);
   if(result.inbox_visible!==size||result.search_matches!==1||!result.focus_retained)throw Error(JSON.stringify(result));
   console.log(JSON.stringify({browser:browser.version(),...result}));await page.close();
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
