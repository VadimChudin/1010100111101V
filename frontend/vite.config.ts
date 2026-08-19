// Dark Mission Control: Vite serves the client workspace while keeping deployment output static.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  root: 'client',
  plugins: [react()],
  build: { outDir: '../dist/public', emptyOutDir: true },
  server: { host: true, port: 3000 },
})
