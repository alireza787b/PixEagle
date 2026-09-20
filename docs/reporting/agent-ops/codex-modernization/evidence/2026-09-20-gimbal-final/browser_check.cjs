// Offline production-browser test: intercept EVERY action; no camera command leaves this page.
const { chromium } = require('../../dashboard/node_modules/playwright');
const fs = require('fs');
const assert = require('assert');
const root = __dirname;
const records = [];
const record = (kind, data) => {
  records.push({ time: Date.now(), kind, data });
  fs.writeFileSync(root + '/browser-events.json', JSON.stringify(records, null, 2));
};
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome' });
  try {
    const actual = JSON.parse(fs.readFileSync('docs/reporting/agent-ops/codex-modernization/evidence/2026-09-20-gimbal-movement-controls/runtime-status.json'));
    record('browser', await browser.version());
    for (const width of [1280, 1200, 768, 390, 320]) {
      const mobile = width < 500;
      const context = await browser.newContext({ viewport: { width, height: mobile ? 844 : 1000 }, hasTouch: mobile, isMobile: mobile });
      const page = await context.newPage();
      page.on('pageerror', error => record('pageerror', error.message));
      const sent = [];
      await page.route('**/api/v1/gimbal/control', route => route.fulfill({ json: { ...actual, connected: true, available: true, reason: null, tracking_state: 'disabled' } }));
      await page.route('**/api/v1/actions/**', async route => {
        const data = route.request().postDataJSON();
        record('intercepted_action', { width, ...data });
        if (!route.request().url().endsWith('/gimbal-control')) throw Error('Unexpected action');
        sent.push(data);
        if (data.direction) await new Promise(resolve => setTimeout(resolve, data.duration_ms || 250));
        await route.fulfill({ json: { status: 'success', result: { success: true } } });
      });
      await page.goto('http://127.0.0.1:3040');
      const movement = page.getByRole('combobox', { name: 'Movement', exact: true });
      await movement.waitFor();
      await movement.selectOption('adjust');
      await page.getByRole('spinbutton', { name: 'Speed (°/s)' }).fill('30');
      await page.getByRole('spinbutton', { name: 'Pulse duration (ms)' }).fill('600');
      await page.waitForTimeout(350);
      await page.getByRole('dialog').screenshot({ path: root + `/adjust-${width}.png` });
      await page.getByRole('button', { name: 'Apply', exact: true }).click();
      assert.equal(sent.length, 0, 'Editing settings must send no command');
      const pan = page.getByRole('button', { name: 'Pan right', exact: true });
      await pan.click();
      await page.waitForTimeout(750);
      assert.equal(sent.length, 1, 'Tap must be one step');
      assert.equal(sent[0].speed_deg_s, 30);
      assert.equal(sent[0].duration_ms, 600);
      await movement.selectOption('fine');
      await pan.scrollIntoViewIfNeeded();
      const bounds = await pan.boundingBox();
      const point = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
      let cdp;
      if (mobile) {
        cdp = await context.newCDPSession(page);
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [point] });
      } else {
        await page.mouse.move(point.x, point.y); await page.mouse.down();
      }
      await page.waitForTimeout(750);
      if (mobile) await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      else await page.mouse.up();
      const afterRelease = sent.filter(action => action.operation === 'pan').length;
      assert(afterRelease >= 3, 'Hold must repeat completed steps');
      await page.waitForTimeout(500);
      assert.equal(sent.filter(action => action.operation === 'pan').length, afterRelease, 'Release must end repetition');
      assert(sent.some(action => action.operation === 'stop'), 'Release from repeat requests Stop');
      await pan.focus();
      await page.keyboard.down('Space');
      await page.waitForTimeout(450);
      await page.keyboard.up('Space');
      await page.waitForTimeout(250);
      const keyboardDone = sent.length;
      await page.waitForTimeout(250);
      assert.equal(sent.length, keyboardDone, 'Key release must end repetition');
      if (mobile) assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'No mobile horizontal overflow');
      const panel = page.getByRole('region', { name: 'External gimbal controls' });
      const sidebarRect = await panel.boundingBox();
      const videoRect = await page.getByRole('button', { name: /fullscreen/i }).first().boundingBox();
      if (width >= 1200) assert(sidebarRect.x > videoRect.x, 'Gimbal card must be beside video');
      else assert(sidebarRect.y > videoRect.y, 'Gimbal card must follow video on narrow screens');
      const rects = {};
      for (const name of ['Pan left', 'Pan right', 'Tilt up', 'Tilt down', 'Center camera', 'Roll −', 'Roll +', 'Zoom in', 'Zoom out', 'Cancel target', 'Stop camera']) {
        const rect = await page.getByRole('button', { name, exact: true }).boundingBox();
        assert(rect.width >= 44 && rect.height >= 44, name + ' touch target');
        rects[name] = rect;
      }
      assert(rects['Tilt up'].y < rects['Center camera'].y && rects['Tilt down'].y > rects['Center camera'].y);
      assert(rects['Pan left'].x < rects['Center camera'].x && rects['Pan right'].x > rects['Center camera'].x);
      assert(rects['Zoom in'].y < rects['Zoom out'].y);
      assert(rects['Roll −'].x < rects['Roll +'].x);
      await pan.evaluate(element => element.blur());
      await page.mouse.move(0, 0);
      await page.waitForTimeout(250);
      await panel.screenshot({ path: root + `/controls-${width}.png` });
      record('layout', { width, rects });
      record('passed', { width, interceptedActions: sent.length, realCameraActions: 0 });
      await context.close();
    }
    assert(!records.some(row => row.kind === 'pageerror'), 'Browser must not report JS errors');
  } finally { await browser.close(); }
})().catch(error => { record('failure', String(error.stack)); console.error(error); process.exitCode = 1; });
