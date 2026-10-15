// What this version does: the list the home page and GET /api/info show.
//
// Add an entry when you add an endpoint, with `new: true` while it is the change being shipped: after the
// deploy, the page shows it under "What this version does".
const FEATURES = [
  { name: 'Describes itself', description: 'Its name, version and commit, as JSON.', endpoint: 'GET /api/info' },
  {
    name: 'Checks its database',
    description: 'The same check as this page, as JSON. Answers 503 when the database is unreachable.',
    endpoint: 'GET /api/db',
  },
];

// The endpoint itself when it is a plain GET, else the API docs, where it can be tried.
function href(feature) {
  const [method, path] = feature.endpoint.split(' ');
  return method === 'GET' && !path.includes(':') && !path.includes('{') ? path : '/docs';
}

module.exports = { FEATURES, href };
