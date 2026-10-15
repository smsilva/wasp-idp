const { build } = require('./app');

async function main() {
  const app = await build({ logger: true });
  await app.listen({ host: '0.0.0.0', port: Number(process.env.PORT || 3000) });
  // The pod stops on SIGTERM: finish the requests in flight, then exit.
  for (const signal of ['SIGTERM', 'SIGINT']) {
    process.once(signal, () => app.close().then(() => process.exit(0)));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
