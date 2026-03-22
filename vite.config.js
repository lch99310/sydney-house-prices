import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Use relative base so the app works regardless of deployment path
// (works for any GitHub Pages repo name or custom domain)
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
