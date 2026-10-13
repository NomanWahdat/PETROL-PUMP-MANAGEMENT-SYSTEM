import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '');
  return {
    plugins: [react()],
    envDir: '..',
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/api': { target: env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
    },
  };
});
