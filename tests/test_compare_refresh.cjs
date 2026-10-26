const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const sourcePath = process.env.WIFI_APP_JS || path.join(__dirname, '../web_measurement_app/static/app.js');
const source = readFileSync(sourcePath, 'utf8').replace(/\ninit\(\)\.catch\([\s\S]*$/, '');
const sample = (scan = 1, ssid = 'Test', bssid = 'aa:bb:cc:dd:ee:01') => [1, scan, ssid, bssid, 36, -50];
const response = (rows, name = 'session_neighbors.csv', total = rows.length) => ({
  ok: true, json: async () => ({ rows, total, neighbor_log_file: name }),
});

function dashboard(fetchImpl) {
  const elements = new Map();
  const timers = [];
  function element(id) {
    if (elements.has(id)) return elements.get(id);
    const value = {
      value: '', checked: false, disabled: false, style: {}, options: [], listeners: {},
      classList: { toggle() {}, add() {}, contains() { return false; } },
      addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); },
      appendChild(option) { this.options.push(option); if (this.options.length === 1) this.value = option.value; },
      set innerHTML(_) { this.options = []; this.value = ''; },
      getContext() { return {}; }, querySelector() { return null; }, querySelectorAll() { return []; },
      closest() { return null; },
    };
    elements.set(id, value);
    return value;
  }
  const radios = ['ping', 'compare'].map(value => Object.assign(element(`radio-${value}`), { value, checked: value === 'ping' }));
  const form = element('config-form');
  form.ssid = { value: 'Test' };
  element('compare-kind-select').value = 'bssid';
  element('compare-top-n').value = '10';
  const requests = [];
  const context = vm.createContext({
    console, setTimeout, clearTimeout,
    window: { addEventListener() {}, setInterval(callback) { timers.push(callback); return timers.length; } },
    document: { getElementById: element, querySelectorAll: () => radios, querySelector: () => null, createElement: () => ({}) },
    fetch: (...args) => { requests.push(args); return fetchImpl(...args); },
  });
  vm.runInContext(source, context, { filename: sourcePath });
  // Rendering is outside these lifecycle tests; retain the real comparison and event code.
  vm.runInContext('renderAll = () => {}; syncExportTitleControls = () => {}; initDisplayControls = () => {}; updateStatus = () => {}; buildPayload = () => ({});', context);
  const api = vm.runInContext('({state, attachEvents, loadLiveNeighborRows, handleStart, handleStop, setCompareRows, buildCompareSegments, toCompareRow})', context);
  api.attachEvents();
  return { ...api, element, radios, timers, requests };
}

async function settle() {
  for (let index = 0; index < 8; index++) await new Promise(resolve => setImmediate(resolve));
}

test('returning to compare after an empty scan fetches completed measurement data', async () => {
  let available = [];
  const app = dashboard(async () => response(available));
  await app.loadLiveNeighborRows();
  assert.equal(app.state.compare.rows.length, 0);
  available = [sample()];
  app.state.running = false;
  app.state.currentMode = 'ping';
  app.radios[1].listeners.change[0]();
  await settle();
  assert.equal(app.state.compare.rows.length, 1);
  assert.equal(app.state.compare.targets.length, 1);
});

test('compare keeps refreshing after measurement stops', async () => {
  let available = [];
  const app = dashboard(async () => response(available));
  await app.loadLiveNeighborRows();
  app.state.currentMode = 'compare';
  app.state.running = false;
  available = [sample()];
  app.timers[0]();
  await settle();
  assert.equal(app.state.compare.rows.length, 1);
});

test('stop collects the final scan even while another plot is selected', async () => {
  let stopping = false;
  const app = dashboard(async url => {
    if (url === '/api/stop') { stopping = true; return { json: async () => ({ current_point: 2 }) }; }
    return response(stopping ? [sample()] : []);
  });
  await app.loadLiveNeighborRows();
  app.state.running = true;
  await app.handleStop();
  assert.equal(app.state.compare.rows.length, 1);
  assert.equal(app.state.running, false);
});

test('a new measurement replaces the previous scan session', async () => {
  let session = 'old';
  const app = dashboard(async url => {
    if (url === '/api/start') { session = 'new'; return { ok: true, json: async () => ({ current_point: 1 }) }; }
    return response([sample(session === 'old' ? 1 : 2)], session);
  });
  await app.loadLiveNeighborRows();
  await app.handleStart();
  assert.equal(app.state.compare.sourceName, 'new');
  assert.equal(app.state.compare.rows.length, 1);
  assert.equal(app.state.compare.rows[0].scan, '2');
});

test('stop refetches scans completed while an earlier request was in flight', async () => {
  let release;
  let count = 0;
  const app = dashboard(url => {
    if (url === '/api/stop') return Promise.resolve({ json: async () => ({ current_point: 2 }) });
    if (++count === 1) return new Promise(resolve => { release = resolve; });
    return Promise.resolve(response([sample(2)], 'session_neighbors.csv', 2));
  });
  const pending = app.loadLiveNeighborRows();
  const stopping = app.handleStop();
  await settle();
  release(response([sample()]));
  await Promise.all([pending, stopping]);
  assert.equal(app.state.compare.rows.length, 2);
  assert.equal(app.state.compare.rows[1].scan, '2');
});

test('overlapping automatic fetches do not duplicate scan rows', async () => {
  let release;
  const app = dashboard(() => new Promise(resolve => { release = resolve; }));
  const first = app.loadLiveNeighborRows();
  const second = app.loadLiveNeighborRows();
  assert.equal(app.requests.length, 1);
  release(response([sample()]));
  await Promise.all([first, second]);
  assert.equal(app.state.compare.rows.length, 1);
});

test('a pending live response cannot replace an imported CSV', async () => {
  let release;
  const app = dashboard(url => url === '/api/stop'
    ? Promise.resolve({ json: async () => ({ current_point: 2 }) })
    : new Promise(resolve => { release = resolve; }));
  const pending = app.loadLiveNeighborRows();
  app.state.compare.source = 'csv';
  app.state.compare.sourceName = 'saved.csv';
  app.setCompareRows([app.toCompareRow(1, 9, 'Saved', 'aa:bb:cc:dd:ee:09', -70)]);
  release(response([sample()]));
  await pending;
  assert.equal(app.state.compare.sourceName, 'saved.csv');
  assert.equal(app.state.compare.rows.length, 1);
  assert.equal(app.state.compare.rows[0].ssid, 'Saved');
  app.state.currentMode = 'compare';
  app.timers[0]();
  app.radios[1].listeners.change[0]();
  await app.handleStop();
  assert.equal(app.requests.filter(([url]) => url.startsWith('/api/neighbors')).length, 1);
});

test('manual refresh waits for an older request and then reloads all rows', async () => {
  let release;
  let count = 0;
  const app = dashboard(() => ++count === 1
    ? new Promise(resolve => { release = resolve; })
    : Promise.resolve(response([sample(), sample(2)])));
  const first = app.loadLiveNeighborRows();
  const manual = app.loadLiveNeighborRows({ reset: true, switchMode: true });
  release(response([sample()]));
  await Promise.all([first, manual]);
  assert.equal(app.state.compare.rows.length, 2);
  assert.equal(app.state.currentMode, 'compare');
  assert.equal(app.requests[1][0], '/api/neighbors?since=0');
});

test('a new session with more rows discards every old row before refetching', async () => {
  let current = false;
  const app = dashboard(async url => current
    ? response(url.endsWith('=0') ? [sample(2), sample(3)] : [sample(3)], 'new', 2)
    : response([sample()], 'old'));
  await app.loadLiveNeighborRows();
  current = true;
  await app.loadLiveNeighborRows();
  assert.equal(app.state.compare.rows.length, 2);
  assert.deepEqual(Array.from(app.state.compare.rows, row => row.scan), ['2', '3']);
});

test('live measurement builds BSSID comparisons for every available route segment', { skip: !process.env.WIFI_COMPARE_LIVE_URL }, async () => {
  const result = await fetch(`${process.env.WIFI_COMPARE_LIVE_URL}/api/neighbors?since=0`);
  assert.ok(result.ok);
  const data = await result.json();
  assert.ok(data.rows.length > 0, 'Start a neighbor-enabled measurement before the optional live check.');
  const app = dashboard(async () => ({ ok: true, json: async () => data }));
  const ssid = process.env.WIFI_COMPARE_SSID || data.rows[0][2];
  app.element('config-form').ssid.value = ssid;
  const validRows = data.rows.filter(([point, , , bssid, , dbm]) =>
    Number.isInteger(Number(point)) && Number(point) > 0 && bssid && Number.isFinite(Number.parseFloat(dbm)));
  const maxPoint = validRows.reduce((maximum, row) => Math.max(maximum, Number(row[0])), 0);
  app.state.points = Array.from({ length: maxPoint + 1 }, (_, index) => ({ x: index * 100, y: index % 2 * 100 }));
  const expectedBssids = new Set(validRows.filter(row => row[2] === ssid).map(row => row[3].toLowerCase()));
  assert.ok(expectedBssids.size > 0, 'The selected SSID must appear in the live scan.');
  await app.loadLiveNeighborRows();
  assert.equal(app.state.compare.rows.length, validRows.length);
  assert.equal(app.state.compare.targets.length, Math.min(10, expectedBssids.size));
  for (const target of app.state.compare.targets) {
    const segments = app.buildCompareSegments(target);
    assert.equal(segments.length, maxPoint);
    assert.ok(segments.every(segment => segment.logs.length > 0));
  }
  console.log(`Live comparison: ${validRows.length} rows, ${app.state.compare.targets.length} BSSIDs, ${maxPoint} segments per target`);
});
