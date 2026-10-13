// Vercel evaluates this configuration before building. No runtime dependency.
const value = process.env.RENDER_BACKEND_URL;
if (!value) throw new Error('Set RENDER_BACKEND_URL to your HTTPS Render service URL in Vercel settings.');
const backend = new URL(value);
if (backend.protocol !== 'https:' || backend.username || backend.password || backend.pathname !== '/' || backend.search || backend.hash) {
  throw new Error('RENDER_BACKEND_URL must be an HTTPS origin without credentials, paths or query parameters.');
}

export const config = {
  framework: 'vite',
  installCommand: 'npm ci',
  buildCommand: 'npm run build',
  outputDirectory: 'dist',
  rewrites: [
    { source: '/api/:path*', destination: `${backend.origin}/api/:path*` },
    { source: '/admin/:path*', destination: `${backend.origin}/admin/:path*` },
    { source: '/static/:path*', destination: `${backend.origin}/static/:path*` },
    { source: '/media/:path*', destination: `${backend.origin}/media/:path*` },
    { source: '/(.*)', destination: '/index.html' },
  ],
  headers: [
    { source: '/api/:path*', headers: [{ key: 'Cache-Control', value: 'no-store' }] },
    { source: '/admin/:path*', headers: [{ key: 'Cache-Control', value: 'no-store' }] },
    { source: '/(.*)', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'same-origin' },
    ] },
  ],
};
