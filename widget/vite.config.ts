import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Widget renders inside a host-injected iframe, so a relative base keeps the
// built asset URLs correct no matter what path the iframe document is served
// from (Cloudflare Pages root or a subpath preview deploy).
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
})
