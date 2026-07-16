import { buildServer } from './server.js';
import { config } from './config.js';

async function main() {
  const app = await buildServer();
  try {
    await app.listen({ port: config.PORT, host: config.HOST });
    app.log.info(`PolyMetl v2 API running at http://${config.HOST}:${config.PORT}`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

main();
