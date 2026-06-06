import { db } from '../db/index.js';

export function resetDb() {
  db.exec(`DELETE FROM experiments;`);
  db.exec(`DELETE FROM api_settings;`);
}
