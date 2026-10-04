'use strict';
// Shared shopping enhancements for the full app and the private preview.
(() => {
  const originalDetail = detail;
  const originalRoute = route;
  const originalRenderBag = renderBag;
  const originalAdd = add;
  const defaultTitle = document.title;
  const productDialog = document.querySelector('#productDialog');
  const isProductRoute = () => location.hash.startsWith('#product/');
  let cartSignature = JSON.stringify(cart);

  // Merely refreshing stock must not discard an in-flight request's retry key.
  saveCart = function () {
    const current = JSON.stringify(cart);
    if (current !== cartSignature) {
      checkoutKey = null;
      lastCheckoutBody = null;
      cartSignature = current;
    }
    try { localStorage.setItem('ras-cart-v2', current); } catch {}
    document.querySelector('#cartCount').textContent = Object.values(cart).reduce((a, b) => a + b, 0);
  };

  function listingState() {
    return { category, search: $('#search').value, brand: $('#brandFilter').value,
      sort: $('#sort').value, y: scrollY, home: !$('#homeView').hidden };
  }

  function restoreListing(saved) {
    category = categories.includes(saved.category) ? saved.category : 'All';
    $('#search').value = saved.search || '';
    $('#brandFilter').value = saved.brand || '';
    $('#sort').value = saved.sort || 'featured';
    $('#homeView').hidden = !saved.home;
    renderProducts();
    requestAnimationFrame(() => scrollTo({ top: Math.max(0, saved.y || 0), behavior: 'instant' }));
  }

  detail = function (id, fromRoute = false) {
    if (!fromRoute) {
      if (!isProductRoute()) {
        history.replaceState({ ...(history.state || {}), rasListing: listingState() }, '', location.href);
        history.pushState({ rasProduct: true }, '', '#product/' + encodeURIComponent(id));
      } else if (location.hash !== '#product/' + id) {
        history.replaceState(history.state, '', '#product/' + encodeURIComponent(id));
      }
    }
    const product = products.find(p => p.id === id);
    if (!product) {
      $('#productDetail').innerHTML = '<div class="empty"><h2 id="productTitle">Product unavailable</h2><p>This item may have changed or is no longer listed.</p><button class="button" data-close="productDialog">Back to the collection</button></div>';
      document.title = 'Product unavailable · RAS';
      modal('productDialog');
      return;
    }
    originalDetail(id);
    document.title = product.name + ' · RAS';
    const copy = document.createElement('div');
    copy.className = 'product-link-actions';
    copy.innerHTML = '<button class="button secondary" type="button" id="copyProductLink">Copy product link</button><button class="text-button" type="button" data-close="productDialog">Continue shopping</button><p id="productLinkStatus" class="muted" role="status"></p>';
    $('#productDetail .detail-copy').append(copy);
    $('#copyProductLink').addEventListener('click', async () => {
      const status = $('#productLinkStatus');
      try {
        await navigator.clipboard.writeText(location.href);
        status.textContent = 'Link copied. This preview remains private to your account.';
        if (!document.querySelector('.topline')?.textContent.includes('PRIVATE')) status.textContent = 'Product link copied.';
      } catch {
        status.textContent = '';
        const field = document.createElement('input');
        field.type = 'url'; field.readOnly = true; field.value = location.href;
        field.setAttribute('aria-label', 'Product link — select and copy');
        field.className = 'copy-link-field'; status.append(field);
        field.focus(); field.select();
      }
    });
  };

  window.removeEventListener('hashchange', originalRoute);
  route = function () {
    if (!products.length) return;
    if (isProductRoute()) {
      const id = location.hash.slice('#product/'.length);
      detail(id, true);
      return;
    }
    if (productDialog.open) productDialog.close();
    document.title = defaultTitle;
    if (history.state?.rasListing) restoreListing(history.state.rasListing);
    else originalRoute();
    const active = location.hash || '#home';
    document.querySelectorAll('.site-header nav a').forEach(a => {
      if (a.getAttribute('href') === active) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  };
  window.addEventListener('hashchange', route);

  productDialog.addEventListener('close', () => {
    if (!isProductRoute()) return;
    if (history.state?.rasProduct) history.back();
    else {
      history.replaceState(null, '', '#shop');
      route();
    }
  });

  add = function (id) {
    if ((cart[id] || 0) >= 99) { toast('Maximum 99 per product. Contact us for larger quantities.'); return; }
    originalAdd(id);
    const button = document.querySelector('#productDetail [data-add="' + id + '"]');
    if (button) button.textContent = 'Added to bag (' + cart[id] + ')';
  };

  renderBag = function () {
    originalRenderBag();
    const rows = getRows();
    if (!rows.length) return;
    const issues = [];
    const unconfirmed = rows.filter(r => !r.product.price_confirmed || r.product.sale_price === null);
    const lowStock = rows.filter(r => r.product.price_confirmed && r.quantity > r.product.stock);
    if (lowStock.length) issues.push('Some selected quantities exceed available stock. You can send an enquiry to check availability.');
    if (unconfirmed.length && !lowStock.length) issues.push('Prices and selling units need confirmation for ' + unconfirmed.length + ' selected product(s).');
    if (issues.length) {
      const note = document.createElement('p'); note.className = 'notice bag-availability';
      note.textContent = issues.join(' '); $('#bagSummary').prepend(note);
    }
    document.querySelectorAll('#bagItems [data-delta="1"]').forEach(b => {
      b.disabled = (cart[b.dataset.quantity] || 0) >= 99;
      if (b.disabled) b.setAttribute('aria-label', 'Maximum quantity reached');
    });
  };

  // Dialogs must not leave the page behind them scrollable on mobile.
  const syncModalState = () => document.documentElement.classList.toggle('dialog-open', !!document.querySelector('dialog[open]'));
  const observer = new MutationObserver(syncModalState);
  document.querySelectorAll('dialog').forEach(d => observer.observe(d, { attributes: true, attributeFilter: ['open'] }));
  if (products.length) route();
})();
