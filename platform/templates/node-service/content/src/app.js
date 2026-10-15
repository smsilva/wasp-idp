// First: the instrumentations patch http before Fastify requires it.
require('./telemetry');

const os = require('node:os');
const Fastify = require('fastify');

const database = require('./database');
const { FEATURES } = require('./features');
const { page } = require('./page');

const THEMES = ['green', 'lime', 'sky', 'violet'];

const featureSchema = {
  type: 'object',
  required: ['name', 'description', 'endpoint'],
  properties: {
    name: { type: 'string' },
    description: { type: 'string' },
    endpoint: { type: 'string' },
    new: { type: 'boolean', default: false },
  },
};

const infoSchema = {
  type: 'object',
  required: ['app', 'title', 'description', 'version', 'commit', 'pod', 'features'],
  properties: {
    app: { type: 'string' },
    title: { type: 'string' },
    description: { type: 'string' },
    version: { type: 'string' },
    commit: { type: 'string' },
    pod: { type: 'string' },
    features: { type: 'array', items: featureSchema },
  },
};

const databaseSchema = {
  type: 'object',
  required: ['status', 'checkedAt', 'details'],
  properties: {
    status: { type: 'string', enum: ['connected', 'failed', 'not-configured'] },
    host: { type: 'string' },
    port: { type: 'integer' },
    database: { type: 'string' },
    user: { type: 'string' },
    serverVersion: { type: 'string' },
    serverAddress: { type: 'string' },
    latencyMs: { type: 'number' },
    error: { type: 'string' },
    checkedAt: { type: 'string', format: 'date-time' },
    details: { type: 'boolean' },
  },
};

// The settings are read when the app is built: the platform sets them as variables of app-spec.yaml, and
// APP_VERSION/APP_COMMIT are baked into the image by platform-build.yaml (Dockerfile ARGs).
function settings() {
  const name = process.env.APP_NAME || 'node-service';
  return {
    app: name,
    title: process.env.APP_TITLE || name,
    description: process.env.APP_DESCRIPTION || '',
    theme: THEMES.includes(process.env.APP_THEME) ? process.env.APP_THEME : THEMES[0],
    version: process.env.APP_VERSION || 'dev',
    commit: process.env.APP_COMMIT || 'unknown',
  };
}

async function build(options = {}) {
  const config = settings();
  const app = Fastify(options);

  await app.register(require('@fastify/swagger'), {
    openapi: {
      info: {
        title: config.title,
        version: config.version,
        description: config.description || `${config.app}, made from the node-service template.`,
      },
    },
  });
  await app.register(require('@fastify/swagger-ui'), { routePrefix: '/docs' });

  const info = () => ({
    app: config.app,
    title: config.title,
    description: config.description,
    version: config.version,
    commit: config.commit,
    pod: os.hostname(),
    features: FEATURES,
  });

  app.get('/', { schema: { hide: true } }, async (request, reply) => {
    const html = page({ info: info(), theme: config.theme, db: await database.check(request.log) });
    return reply.type('text/html; charset=utf-8').send(html);
  });

  app.get(
    '/api/info',
    { schema: { tags: ['about'], summary: 'Name, version and commit of this build', response: { 200: infoSchema } } },
    async () => info(),
  );

  app.get(
    '/api/db',
    {
      schema: {
        tags: ['about'],
        summary: 'Check the connection to the database',
        response: { 200: databaseSchema, 503: { description: 'The database is unreachable', ...databaseSchema } },
      },
    },
    async (request, reply) => {
      const status = await database.check(request.log);
      return reply.code(status.status === 'failed' ? 503 : 200).send(status);
    },
  );

  app.get(
    '/healthz',
    {
      schema: {
        tags: ['about'],
        summary: 'Liveness and readiness; never touches the database',
        response: { 200: { type: 'object', properties: { status: { type: 'string' } } } },
      },
    },
    async () => ({ status: 'ok' }),
  );

  app.get('/openapi.json', { schema: { hide: true } }, async () => app.swagger());

  return app;
}

module.exports = { build, THEMES };
