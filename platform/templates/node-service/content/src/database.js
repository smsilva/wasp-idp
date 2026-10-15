// The database check behind the home page and GET /api/db.
//
// The platform sets DATABASE_* from the `db` resource of app-spec.yaml (Score); without DATABASE_HOST there
// is nothing to check. Each check opens its own short connection, so the page shows the state at the
// moment it loaded: a database that went away turns the page red on the next reload.
//
// Host, user, server address and the driver's error are shown only with SHOW_DATABASE_DETAILS=true: they
// help a demo and an attacker alike. The error always goes to the log.
const { Client } = require('pg');

const TIMEOUT_MS = 2000;

function showDetails() {
  return (process.env.SHOW_DATABASE_DETAILS || 'false').toLowerCase() === 'true';
}

// The state of the database; without SHOW_DATABASE_DETAILS, only the state and the latency.
async function check(log) {
  const status = await connect();
  if (status.status === 'failed') {
    log?.warn(`database check failed: ${status.host}:${status.port}/${status.database} as ${status.user}: ${status.error}`);
  }
  if (showDetails()) {
    return { ...status, details: true };
  }
  return withoutEmpty({ status: status.status, latencyMs: status.latencyMs, checkedAt: status.checkedAt, details: false });
}

async function connect() {
  const host = process.env.DATABASE_HOST || null;
  const target = {
    host,
    port: Number(process.env.DATABASE_PORT || 5432),
    database: process.env.DATABASE_NAME || null,
    user: process.env.DATABASE_USER || null,
    checkedAt: new Date().toISOString(),
  };
  if (host === null) {
    return withoutEmpty({ status: 'not-configured', ...target });
  }
  const password = process.env.DATABASE_PASSWORD || '';
  const client = new Client({
    ...target,
    password,
    connectionTimeoutMillis: TIMEOUT_MS,
    query_timeout: TIMEOUT_MS,
    application_name: process.env.APP_NAME || 'node-service',
  });
  // A broken connection emits 'error' after connect; without a listener it would crash the process.
  client.on('error', () => {});
  const started = performance.now();
  try {
    await client.connect();
    const { rows } = await client.query(
      "SELECT current_setting('server_version') AS version, host(inet_server_addr()) AS address, inet_server_port() AS port",
    );
    const latencyMs = Math.round((performance.now() - started) * 10) / 10;
    const { version, address, port } = rows[0];
    return withoutEmpty({
      status: 'connected',
      ...target,
      serverVersion: version,
      serverAddress: address ? `${address}:${port}` : null,
      latencyMs,
    });
  } catch (error) {
    let message = (error.message || '').trim() || error.code || error.name;
    if (password) {
      message = message.replaceAll(password, '***');
    }
    return withoutEmpty({ status: 'failed', ...target, error: message });
  } finally {
    await client.end().catch(() => {});
  }
}

// The JSON leaves out what is not known, as the python-service template does.
function withoutEmpty(object) {
  return Object.fromEntries(Object.entries(object).filter(([, value]) => value !== null && value !== undefined));
}

module.exports = { check, TIMEOUT_MS };
