const assert = require('node:assert/strict');
const { test } = require('node:test');

const { app, freePort } = require('./helpers');

test('without host the database is not configured', async (t) => {
  const c = await app(t);
  const response = await c.inject('/api/db');
  assert.equal(response.statusCode, 200);
  assert.equal(response.json().status, 'not-configured');
  assert.ok((await c.inject('/')).body.includes('No database configured'));
});

async function unreachable() {
  return {
    DATABASE_HOST: '127.0.0.1',
    DATABASE_PORT: String(await freePort()),
    DATABASE_NAME: 'app',
    DATABASE_USER: 'app',
    DATABASE_PASSWORD: 's3cret-value',
  };
}

test('an unreachable database fails in red without details by default', async (t) => {
  const logged = [];
  const c = await app(t, await unreachable());
  c.addHook('onRequest', async (request) => {
    request.log = { warn: (message) => logged.push(message) };
  });
  const response = await c.inject('/api/db');
  assert.equal(response.statusCode, 503);
  const body = response.json();
  assert.deepEqual([body.status, body.details], ['failed', false]);
  assert.deepEqual(Object.keys(body).sort(), ['checkedAt', 'details', 'status']);
  const page = (await c.inject('/')).body;
  assert.ok(page.includes('data-state="failed"'));
  assert.ok(!page.includes('127.0.0.1'));
  // The error goes to the log, never the password.
  assert.ok(logged.join('\n').includes('127.0.0.1'));
  assert.ok(!logged.join('\n').includes('s3cret-value'));
});

test('details show the target and the error without the password', async (t) => {
  const c = await app(t, { ...(await unreachable()), SHOW_DATABASE_DETAILS: 'true' });
  const response = await c.inject('/api/db');
  assert.equal(response.statusCode, 503);
  const body = response.json();
  assert.deepEqual([body.status, body.details, body.host], ['failed', true, '127.0.0.1']);
  assert.ok(body.error);
  assert.ok(!response.body.includes('s3cret-value'));
  const page = (await c.inject('/')).body;
  assert.ok(page.includes("Can't reach the database"));
  assert.ok(page.includes('127.0.0.1'));
  assert.ok(!page.includes('s3cret-value'));
});

test('a reachable database connects', { skip: !process.env.DATABASE_HOST && 'needs a PostgreSQL: set DATABASE_HOST, as CI does' }, async (t) => {
  const c = await app(t, { SHOW_DATABASE_DETAILS: 'true' }, { withDatabase: true });
  const body = (await c.inject('/api/db')).json();
  assert.equal(body.status, 'connected', body.error);
  assert.ok(body.serverVersion);
  assert.ok(body.latencyMs >= 0);
  assert.ok((await c.inject('/')).body.includes('Connected to PostgreSQL'));
});
