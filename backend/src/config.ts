export const config = {
  PORT: parseInt(process.env.PORT || '8765', 10),
  HOST: process.env.HOST || '127.0.0.1',
  DATA_DIR: process.env.DATA_DIR || './data',
  NODE_ENV: process.env.NODE_ENV || 'production',
  GAMMA_API_BASE: 'https://gamma-api.polymarket.com',
};
