// PandaDoc signed-PDF extractor.
// Run the WHOLE body of this file as the `function` argument of mcp__playwright__browser_evaluate
// while the PandaDoc public view (app.pandadoc.com/document/v2?token=...) is loaded.
// PD_TOKEN / PD_DOC_ID / CONTENT_UUID are auto-discovered when left empty.
// Triggers two downloads (land in .playwright-mcp/): byte-exact source PDF + signed reconstruction.
// Returns diagnostics; measurements are stashed in window.__pdFields for inspection.
async () => {
  // ---------- config (auto-discovered when empty) ----------
  let PD_TOKEN = '';
  let PD_DOC_ID = '';
  let CONTENT_UUID = '';
  const OUT_BASENAME = (document.title.replace(/\s*-\s*PandaDoc\s*$/, '').trim() || 'pandadoc-document')
    .replace(/\s*\.(docx?|pdf)\s*$/i, '').trim();

  const log = { steps: [] };
  const fail = (msg, extra) => ({ error: msg, ...extra, log });

  if (!PD_TOKEN) PD_TOKEN = new URLSearchParams(location.search).get('token') || '';
  if (!PD_TOKEN) return fail('no token in page URL; set PD_TOKEN');
  if (!PD_DOC_ID) {
    const m = performance.getEntriesByType('resource').map(e => e.name).join(' ')
      .match(/documents\/([A-Za-z0-9]{22})/);
    PD_DOC_ID = m && m[1];
  }
  if (!PD_DOC_ID) return fail('doc id not found in resource log; set PD_DOC_ID');
  log.steps.push({ token: PD_TOKEN.slice(0, 6) + '…', docId: PD_DOC_ID });

  // ---------- 1. content JWT ----------
  const tr = await fetch(`https://api.pandadoc.com/org/null/ws/null/documents/${PD_DOC_ID}/content_token`,
    { headers: { authorization: 'X-Token ' + PD_TOKEN } });
  if (!tr.ok) return fail('content_token HTTP ' + tr.status);
  const jwt = await tr.json(); // bare string, not {token}
  if (!CONTENT_UUID) {
    try {
      const p = JSON.parse(atob(jwt.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      log.jwtClaims = Object.keys(p);
      CONTENT_UUID = p.content_uuid || p.aud ||
        Object.values(p).find(v => typeof v === 'string' && /^[0-9a-f-]{36}$/.test(v)) || '';
    } catch (e) { return fail('JWT decode: ' + e.message); }
  }
  if (!CONTENT_UUID) return fail('content_uuid not found in JWT; set CONTENT_UUID');

  // ---------- 2. WS content_fetch ----------
  const content = await new Promise((resolve, reject) => {
    const ws = new WebSocket('wss://websocket.pandadoc.com/ws');
    const to = setTimeout(() => reject(new Error('ws timeout')), 25000);
    ws.onerror = () => { clearTimeout(to); reject(new Error('ws error')); };
    ws.onopen = () => ws.send(JSON.stringify({
      id: 1, endpoint: 'authorize',
      payload: { token: jwt, appVersion: '6a66b5d417ba' }, topic: 'permissions'
    }));
    ws.onmessage = (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id === 1 && msg.error) { clearTimeout(to); reject(new Error('ws auth: ' + JSON.stringify(msg.error))); return; }
      if (msg.id === 1) {
        ws.send(JSON.stringify({
          id: 2, endpoint: 'content_fetch',
          payload: { content_uuid: CONTENT_UUID, tag_uuid: null, resolve_s3_links: true }, topic: 'events'
        }));
        return;
      }
      if (msg.id === 2 && msg.payload && msg.payload.content) {
        clearTimeout(to); ws.close(); resolve(msg.payload.content);
      }
    };
  }).catch(e => ({ __err: e.message }));
  if (content.__err) return fail(content.__err);
  log.steps.push('content fetched');

  // ---------- 3. source PDF bytes ----------
  const pdfItem = content.pdf && content.pdf.items && content.pdf.items[0];
  if (!pdfItem || !pdfItem.source_pdf) return fail('no pdf.items[0].source_pdf in content');
  const pr = await fetch(pdfItem.source_pdf);
  if (!pr.ok) return fail('source_pdf HTTP ' + pr.status);
  const srcBytes = new Uint8Array(await pr.arrayBuffer());
  log.srcBytes = srcBytes.length;

  // ---------- 4. measure field overlays while scrolling (viewer may virtualize) ----------
  // DOM structure (verified 2026-09-17): each page = div[class*=sectionItemBox] holding
  // one img[src*=pdf-pages] (page background; its rect == the 816x1056 page rect) plus
  // that page's field overlays. Fields live in div[class*=fieldUI] containers:
  // signature fields hold img[src*=field-storage]; date/text fields hold leaf text nodes.
  // NB: div[class*=pageLayoutRoot] does NOT contain the page img or the fields — do not
  // scope queries to it. Assign fields to pages geometrically (center-point containment).
  const findScroller = () => [...document.querySelectorAll('*')]
    .filter(e => e.scrollHeight > e.clientHeight + 100 && e.clientHeight > 200)
    .sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
  const pages = {}; // pageNum -> {w,h, imgs:[], texts:[], _seen:{}}
  const leafTexts = (root) => [...root.querySelectorAll('*')]
    .filter(e => e.children.length === 0 && e.textContent.trim() && e.getBoundingClientRect().height > 0);
  const pageOf = (r, pageRects) => pageRects.find(p =>
    r.x + r.width / 2 >= p.r.x && r.x + r.width / 2 <= p.r.right &&
    r.y + r.height / 2 >= p.r.y && r.y + r.height / 2 <= p.r.bottom);
  const collect = () => {
    const pageRects = [];
    for (const pimg of document.querySelectorAll('img[src*=pdf-pages]')) {
      const m = pimg.src.match(/%2F(\d+)%2F\d+\.jpg/) || pimg.src.match(/\/(\d+)\/\d+\.jpg/);
      if (!m) continue;
      const r = pimg.getBoundingClientRect();
      if (r.width < 100) continue; // not laid out yet
      const n = +m[1];
      pageRects.push({ n, r });
      if (!pages[n]) pages[n] = { w: r.width, h: r.height, imgs: [], texts: [], _seen: {} };
    }
    for (const s of document.querySelectorAll('img[src*=field-storage]')) {
      const r = s.getBoundingClientRect();
      if (!r.width) continue;
      const p = pageOf(r, pageRects);
      if (!p) continue;
      const key = 'i:' + s.src;
      if (pages[p.n]._seen[key]) continue;
      pages[p.n]._seen[key] = 1;
      pages[p.n].imgs.push({ src: s.src, x: r.x - p.r.x, y: r.y - p.r.y, w: r.width, h: r.height });
    }
    for (const f of document.querySelectorAll('div[class*=fieldUI]')) {
      if (f.querySelector('img[src*=field-storage]')) continue; // signature handled above
      for (const t of leafTexts(f)) {
        const r = t.getBoundingClientRect();
        const p = pageOf(r, pageRects);
        if (!p) continue;
        const rel = { x: r.x - p.r.x, y: r.y - p.r.y };
        const key = 't:' + t.textContent.trim() + '@' + Math.round(rel.x) + ',' + Math.round(rel.y);
        if (pages[p.n]._seen[key]) continue;
        pages[p.n]._seen[key] = 1;
        const cs = getComputedStyle(t);
        pages[p.n].texts.push({
          s: t.textContent.trim(), x: rel.x, y: rel.y, w: r.width, h: r.height,
          font: cs.fontFamily, size: parseFloat(cs.fontSize), weight: +cs.fontWeight || 400,
          style: cs.fontStyle, color: cs.color,
          lineH: cs.lineHeight === 'normal' ? 1.2 * parseFloat(cs.fontSize) : parseFloat(cs.lineHeight)
        });
      }
    }
  };
  // Scroll passes until every expected page is measured and the field total
  // stops growing (pages/fields may mount lazily while scrolling).
  const expectedPages = ((content.content && content.content.items) || [])
    .reduce((n, s) => n + ((s.items || []).length), 0) || null;
  log.expectedPages = expectedPages;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const t0 = Date.now();
  let pass = 0, lastFieldTotal = -1, stable = 0;
  while (Date.now() - t0 < 60000) {
    pass++;
    const sc = findScroller();
    if (sc) {
      for (let y = 0; y <= sc.scrollHeight; y += 500) { sc.scrollTop = y; await sleep(180); collect(); }
      sc.scrollTop = 0;
    } else {
      collect();
      await sleep(400);
    }
    const got = Object.keys(pages).length;
    const fieldTotal = Object.values(pages).reduce((n, p) => n + p.imgs.length + p.texts.length, 0);
    stable = fieldTotal === lastFieldTotal ? stable + 1 : 0;
    lastFieldTotal = fieldTotal;
    if (got && (!expectedPages || got >= expectedPages) && stable >= 1) break;
  }
  log.passes = pass;
  if (!Object.keys(pages).length) return fail('no pdf-pages imgs found — viewer not rendered? reload and retry');
  for (const p of Object.values(pages)) delete p._seen;
  window.__pdFields = pages;
  log.pagesMeasured = Object.keys(pages).map(Number).sort((a, b) => a - b);
  log.imgCount = Object.values(pages).reduce((n, p) => n + p.imgs.length, 0);
  log.textCount = Object.values(pages).reduce((n, p) => n + p.texts.length, 0);

  // ---------- 5. pdf-lib ----------
  if (!window.PDFLib) {
    const src = await (await fetch('https://unpkg.com/pdf-lib@1.17.1/dist/pdf-lib.min.js')).text();
    (0, eval)(src);
  }
  const { PDFDocument, StandardFonts, rgb } = window.PDFLib;
  const pdfDoc = await PDFDocument.load(srcBytes);
  const pdfPages = pdfDoc.getPages();
  log.pdfPages = pdfPages.length;
  log.pdfSize = [pdfPages[0].getWidth(), pdfPages[0].getHeight()];

  const fontNameFor = (t) => {
    const bold = t.weight >= 600, ital = /italic|oblique/i.test(t.style);
    if (/times/i.test(t.font)) return 'Times' + (bold && ital ? '-BoldItalic' : bold ? '-Bold' : ital ? '-Italic' : '-Roman');
    if (/courier/i.test(t.font)) return 'Courier' + (bold && ital ? '-BoldOblique' : bold ? '-Bold' : ital ? '-Oblique' : '');
    return 'Helvetica' + (bold && ital ? '-BoldOblique' : bold ? '-Bold' : ital ? '-Oblique' : '');
  };
  const fontCache = {};
  const fontFor = async (t) => {
    const name = fontNameFor(t);
    if (!fontCache[name]) fontCache[name] = await pdfDoc.embedFont(StandardFonts[name] || StandardFonts.Helvetica);
    return fontCache[name];
  };
  const parseRgb = (c) => {
    const m = c.match(/[\d.]+/g) || [0, 0, 0];
    return rgb(m[0] / 255, m[1] / 255, m[2] / 255);
  };
  const imgCache = {};
  for (const [n, rec] of Object.entries(pages)) {
    const pg = pdfPages[n - 1];
    if (!pg) { log['skipPage' + n] = 'no such pdf page'; continue; }
    const sx = pg.getWidth() / rec.w, sy = pg.getHeight() / rec.h;
    for (const im of rec.imgs) {
      if (!imgCache[im.src]) {
        const ir = await fetch(im.src).catch(() => null);
        if (!ir || !ir.ok) return fail('field image fetch failed (HTTP ' + (ir && ir.status) + ') — presigned URL stale? reload the page and re-run immediately');
        const b = new Uint8Array(await ir.arrayBuffer());
        imgCache[im.src] = (b[0] === 0xFF && b[1] === 0xD8) ? await pdfDoc.embedJpg(b) : await pdfDoc.embedPng(b);
      }
      pg.drawImage(imgCache[im.src], { x: im.x * sx, y: pg.getHeight() - (im.y + im.h) * sy, width: im.w * sx, height: im.h * sy });
    }
    for (const t of rec.texts) {
      const baseline = t.y + (t.lineH - t.size) / 2 + 0.9 * t.size;
      pg.drawText(t.s, {
        x: t.x * sx, y: pg.getHeight() - baseline * sy,
        size: t.size * sy, font: await fontFor(t), color: parseRgb(t.color)
      });
    }
  }

  // ---------- 6. download both ----------
  const out = await pdfDoc.save();
  const dl = (bytes, name) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
  };
  dl(out, OUT_BASENAME + ' (signed-reconstruction).pdf');
  await new Promise(r => setTimeout(r, 800));
  dl(srcBytes, OUT_BASENAME + ' (pandadoc-source-unsigned).pdf');
  log.outBytes = out.length;
  return log;
}
