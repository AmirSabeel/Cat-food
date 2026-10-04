// Optional browser regression suite. Requires Playwright and a running local store.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.RAS_TEST_URL || 'http://127.0.0.1:8000';
if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) throw Error('Run these checks only against a local test store.');
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.RAS_BROWSER_PATH ? { executablePath: process.env.RAS_BROWSER_PATH } : {}),
    args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/#shop');
    await page.waitForSelector('.product-card');
    assert.equal(await page.locator('.product-card').count(), 84);
    await page.getByRole('button', { name: 'Groceries', exact: true }).click();
    await page.fill('#search', 'peanut');
    assert.equal(await page.locator('.product-card').count(), 4);
    await page.locator('.product-image-button').first().click();
    await page.waitForSelector('#productDialog[open]');
    assert.match(page.url(), /#product\/\d{13}$/);
    const productUrl = page.url();
    assert.match(await page.title(), /Peanut/i);
    await page.click('#copyProductLink');
    await page.waitForFunction(() => document.querySelector('#productLinkStatus')?.textContent || document.querySelector('.copy-link-field'));
    assert(await page.locator('#productLinkStatus').textContent() || await page.locator('.copy-link-field').count());
    assert(await page.locator('html').evaluate(e => e.classList.contains('dialog-open')));
    await page.goBack();
    await page.waitForSelector('#productDialog:not([open])', { state: 'attached' });
    assert.equal(await page.locator('#search').inputValue(), 'peanut');
    assert.equal(await page.locator('.chip.active').textContent(), 'Groceries');
    assert.equal(await page.locator('.product-card').count(), 4);
    await page.goForward();
    await page.waitForSelector('#productDialog[open]');
    await page.keyboard.press('Escape');
    await page.waitForURL('**/#shop');
    assert.equal(await page.locator('#search').inputValue(), 'peanut');
    // Reloaded/shared links work without a preceding listing history entry.
    const fresh = await browser.newPage({ viewport: { width: 390, height: 844 } });
    fresh.on('pageerror', e => errors.push(e.message));
    await fresh.goto(productUrl);
    await fresh.waitForSelector('#productDialog[open]');
    await fresh.locator('#productDetail [data-add]').click();
    assert.match(await fresh.locator('#productDetail [data-add]').textContent(), /Added to bag \(1\)/);
    await fresh.locator('[data-close="productDialog"]').first().click();
    await fresh.waitForURL('**/#shop');
    await fresh.click('#cartButton');
    await fresh.waitForSelector('#bagDialog[open]');
    assert.equal(await fresh.locator('.bag-row').count(), 1);
    await fresh.locator('[data-close="bagDialog"]').first().click();
    const id = productUrl.split('/').pop();
    const result = await fresh.evaluate(id => {
      checkoutKey = 'keep-this-key'; lastCheckoutBody = 'same-request'; saveCart();
      const kept = checkoutKey === 'keep-this-key';
      cart[id] = 99; saveCart();
      return { kept, invalidated: checkoutKey === null };
    }, id);
    assert.deepEqual(result, { kept: true, invalidated: true });
    await fresh.click('#cartButton');
    await fresh.waitForSelector('#bagDialog[open]');
    assert(await fresh.locator('[data-delta="1"]').isDisabled());
    assert(await fresh.locator('[data-delta="1"]').evaluate(e => e.getBoundingClientRect().width >= 44));
    await fresh.locator('[data-close="bagDialog"]').first().click();
    await fresh.goto(base + '/#product/not-a-real-product');
    await fresh.waitForSelector('#productDialog[open]');
    assert.equal(await fresh.locator('#productTitle').textContent(), 'Product unavailable');
    await fresh.locator('[data-close="productDialog"]').first().click();
    await fresh.waitForURL('**/#shop');
    assert.equal(await fresh.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    console.log('PASS: product links, reload, Back/Forward/Escape, restored filters, copy link, bag feedback, retry keys, quantity limit, touch targets, unavailable-product state and mobile width.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
