const net = require('node:net');

const { build } = require('../src/app');

const SETTINGS = ['APP_NAME', 'APP_TITLE', 'APP_DESCRIPTION', 'APP_THEME', 'APP_VERSION', 'APP_COMMIT', 'SHOW_DATABASE_DETAILS'];
const DATABASE = ['DATABASE_HOST', 'DATABASE_PORT', 'DATABASE_NAME', 'DATABASE_USER', 'DATABASE_PASSWORD'];

// The app as the environment sets it; withDatabase keeps the DATABASE_* that CI exports.
async function app(t, environment = {}, { withDatabase = false } = {}) {
  const saved = { ...process.env };
  for (const key of [...SETTINGS, ...(withDatabase ? [] : DATABASE)]) {
    delete process.env[key];
  }
  Object.assign(process.env, environment);
  const instance = await build();
  t.after(async () => {
    await instance.close();
    process.env = saved;
  });
  return instance;
}

// A port nothing listens on: the connection is refused at once.
function freePort() {
  return new Promise((resolve) => {
    const probe = net.createServer().listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

module.exports = { app, freePort };
