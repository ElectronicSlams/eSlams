/* Run with Playwright on NODE_PATH and generated pages as the first argument. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(process.argv[2]);
  const files = fs.readdirSync(root).filter(name => name.endsWith('.html')).sort();
  assert.equal(files.length, 50);
  const browser = await chromium.launch({headless: true});
  let checks = 0;
  try {
    for (const width of [390, 768, 1440]) {
      const page = await browser.newPage({viewport: {width, height: 900}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      for (const name of files) {
        await page.goto(pathToFileURL(path.join(root, name)).href);
        assert.equal(errors.length, 0, `${name} script errors`);
        const inspect = async () => {
          const data = await page.evaluate(() => ({
            width: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            targets: [...document.querySelectorAll('button.move')].map(b => b.getBoundingClientRect().height),
            table: document.querySelectorAll('#board [role="table"]').length,
            cells: [...document.querySelectorAll('#board [role="cell"]')].map(c => c.getAttribute('aria-label')),
            summary: document.querySelectorAll('#board .state-summary dl').length,
            raw: document.querySelectorAll('#board pre').length,
            details: document.getElementById('details').innerText,
            chess: Boolean((events[selected] || {}).public_state?.fen),
          }));
          assert(data.width <= data.viewport, `${name} overflow ${data.width}/${width}`);
          assert(data.targets.every(height => height >= 24), `${name} small targets`);
          assert(data.table || data.summary, `${name} missing public state presentation`);
          assert(data.cells.every(label => label && label.length > 0), `${name} unlabeled cell`);
          assert.equal(data.raw, 0, `${name} raw JSON fallback`);
          if (!data.chess) assert(!data.details.includes('FEN') && !data.details.includes('checkmate'), `${name} chess details`);
          checks++;
        };
        await inspect();
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'play', `${name} controls not first`);
        const before = await page.evaluate(() => selected);
        await page.keyboard.press('ArrowRight');
        assert.equal(await page.evaluate(() => selected), before + 1, `${name} arrow navigation`);
        assert.equal(await page.evaluate(() => document.activeElement.id), 'play', `${name} control lost focus`);
        const move = page.locator('button.move').first();
        if (await move.count()) {
          await move.focus();
          const index = await move.getAttribute('data-event-index');
          await page.keyboard.press('Enter');
          assert.equal(await page.evaluate(() => document.activeElement.dataset.eventIndex), index, `${name} move lost focus`);
        }
        await page.keyboard.press('End');
        await inspect();
        assert.equal(await page.locator('#turnStatus').getAttribute('aria-live'), 'polite');
        // Check numeric zero at its actual event, rather than a source-string assertion.
        const zero = await page.evaluate(() => events.findIndex(event => event.action === 0));
        if (zero > 0) {
          await page.evaluate(index => setSelected(index), zero);
          assert.equal(await page.evaluate(() => labelForAction(currentMove())), '0', `${name} zero action identity`);
        }
      }
      const unsafe = await page.evaluate(() => {
        const board = document.getElementById('board');
        board.innerHTML = renderChess({public_state: {fen: '<img src=x onerror=alert(1)>/8/8/8/8/8/8/8'}});
        const chessImages = board.querySelectorAll('img').length;
        board.innerHTML = renderSummary({'<img src=x>': {value: '<img src=x onerror=alert(1)>'}});
        return chessImages + board.querySelectorAll('img').length;
      });
      assert.equal(unsafe, 0, 'untrusted public state must stay escaped');
      await page.close();
    }
    const securityPage = await browser.newPage();
    await securityPage.goto(pathToFileURL(path.join(root, "security/escaped.html")).href);
    assert.equal(await securityPage.evaluate(() => Boolean(window.eslamsInjected)), false, "mixed-case script close must be inert");
    assert.equal(await securityPage.locator("img").count(), 0, "untrusted state text must not create elements");
    assert((await securityPage.locator("#board").innerText()).includes("</SCRIPT>"));
    await securityPage.close();
    console.log(`${files.length} arenas passed ${checks} initial/final viewport checks plus keyboard/focus/zero-label regressions`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
