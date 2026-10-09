const API_PORT = 8090;
const BASE_URL = `http://127.0.0.1:${API_PORT}`;
const quotesList = document.getElementById('quotes');
const updatedLabel = document.getElementById('updated');
const message = document.getElementById('message');
const refreshButton = document.getElementById('refresh');
const dashboardLink = document.getElementById('dashboard');

function formatPrice(value) {
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function makeQuoteRow(quote) {
  const item = document.createElement('li');
  item.className = 'quote';

  const identity = document.createElement('div');
  identity.className = 'identity';
  const symbol = document.createElement('span');
  symbol.className = 'symbol';
  symbol.textContent = String(quote.symbol || '—');
  if (quote.stale) symbol.classList.add('stale');
  const name = document.createElement('span');
  name.className = 'name';
  name.textContent = String(quote.name || quote.group || '');
  identity.append(symbol, name);

  const values = document.createElement('div');
  values.className = 'values';
  const price = document.createElement('div');
  price.className = 'price';
  price.textContent = formatPrice(quote.price);
  const change = document.createElement('div');
  const pct = quote.chg_pct;
  const validChange = Number.isFinite(pct);
  change.className = `change ${validChange && pct > 0 ? 'up' : validChange && pct < 0 ? 'down' : 'flat'}`;
  change.textContent = validChange ? `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%` : (quote.error ? '暂不可用' : '—');
  values.append(price, change);
  item.append(identity, values);
  return item;
}

async function refreshQuotes() {
  refreshButton.disabled = true;
  updatedLabel.textContent = '正在连接…';
  message.hidden = true;
  quotesList.replaceChildren();

  try {
    const response = await fetch(`${BASE_URL}/data/quotes.json?_=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = await response.json();
    if (!Array.isArray(snapshot.quotes)) throw new Error('行情格式无效');

    const fragment = document.createDocumentFragment();
    for (const quote of snapshot.quotes) fragment.append(makeQuoteRow(quote));
    quotesList.replaceChildren(fragment);
    updatedLabel.textContent = snapshot.updated
      ? `更新于 ${new Date(snapshot.updated * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
      : '行情已载入';
    if (!snapshot.quotes.length) {
      message.textContent = '观察池暂无代码。';
      message.hidden = false;
    }
  } catch (_error) {
    updatedLabel.textContent = '本机服务未连接';
    message.textContent = '请先安装并启动 Market Glance，再试一次。';
    message.hidden = false;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener('click', refreshQuotes);
dashboardLink.href = `${BASE_URL}/`;
refreshQuotes();
