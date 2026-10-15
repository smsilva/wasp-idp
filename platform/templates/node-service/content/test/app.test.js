const assert = require('node:assert/strict');
const { test } = require('node:test');

const { app } = require('./helpers');

test('healthz returns ok', async (t) => {
  const response = await (await app(t)).inject('/healthz');
  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.json(), { status: 'ok' });
});

test('info reads the environment', async (t) => {
  const c = await app(t, { APP_NAME: 'hello-alpha', APP_TITLE: 'Hello Alpha', APP_VERSION: '0.2.0', APP_COMMIT: 'b5f9569abc' });
  const body = (await c.inject('/api/info')).json();
  assert.equal(body.app, 'hello-alpha');
  assert.equal(body.title, 'Hello Alpha');
  assert.deepEqual([body.version, body.commit], ['0.2.0', 'b5f9569abc']);
  assert.deepEqual(body.features.slice(0, 2).map((feature) => feature.endpoint), ['GET /api/info', 'GET /api/db']);
});

test('info falls back to defaults', async (t) => {
  const body = (await (await app(t)).inject('/api/info')).json();
  assert.deepEqual([body.app, body.title, body.version, body.commit], ['node-service', 'node-service', 'dev', 'unknown']);
});

test('home page shows title, theme, version, runtime and features', async (t) => {
  const c = await app(t, { APP_NAME: 'hello-alpha', APP_TITLE: 'Hello Alpha', APP_THEME: 'sky', APP_VERSION: '0.2.0-greetings.b5f9569' });
  const response = await c.inject('/');
  assert.equal(response.statusCode, 200);
  assert.match(response.headers['content-type'], /^text\/html/);
  const page = response.body;
  assert.ok(page.includes('<h1>Hello Alpha</h1>'));
  assert.ok(page.includes('data-theme="sky"'));
  assert.ok(page.includes('0.2.0-greetings.b5f9569'));
  assert.ok(page.includes(`Node.js ${process.versions.node}`));
  assert.ok(page.includes('Checks its database'));
  assert.ok(page.includes('href="/docs"'));
});

test('an unknown theme falls back to the first', async (t) => {
  const page = (await (await app(t, { APP_THEME: 'indigo' })).inject('/')).body;
  assert.ok(page.includes('data-theme="green"'));
});

test('home page escapes the title', async (t) => {
  const page = (await (await app(t, { APP_TITLE: '<script>x</script>' })).inject('/')).body;
  assert.ok(!page.includes('<script>'));
});

test('swagger documents the api', async (t) => {
  const c = await app(t);
  assert.equal((await c.inject('/docs')).statusCode < 400, true);
  const paths = Object.keys((await c.inject('/openapi.json')).json().paths);
  for (const path of ['/api/info', '/api/db', '/healthz']) {
    assert.ok(paths.includes(path), path);
  }
  assert.ok(!paths.includes('/'));
});
