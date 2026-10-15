const assert = require('node:assert/strict');
const http = require('node:http');
const { test } = require('node:test');

const { app } = require('./helpers');

// The contract of the platform's routing (ADR 0035): a fetch() made while handling a request carries that
// request's baggage, so a route by baggage holds down the whole chain of calls. Real sockets on both
// ends: inject() skips the http server, where the incoming context is read.
test('outgoing calls carry the incoming baggage', async (t) => {
  const received = [];
  const backend = http.createServer((request, response) => {
    received.push(request.headers);
    response.end();
  });
  await new Promise((resolve) => backend.listen(0, '127.0.0.1', resolve));
  t.after(() => backend.close());
  const backendUrl = `http://127.0.0.1:${backend.address().port}/`;

  const c = await app(t);
  c.get('/chain', async () => ({ status: (await fetch(backendUrl)).status }));
  const address = await c.listen({ host: '127.0.0.1', port: 0 });

  const response = await fetch(`${address}/chain`, { headers: { baggage: 'sandbox=pr-42' } });
  assert.deepEqual(await response.json(), { status: 200 });
  assert.equal(received[0].baggage, 'sandbox=pr-42');

  received.length = 0;
  await fetch(`${address}/chain`);
  assert.equal(received[0].baggage, undefined);
});
