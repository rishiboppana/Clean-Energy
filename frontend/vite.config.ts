import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { fs: { allow: ['..'] } }, // lets the app import ../data/hubs.json
})
