import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['three'] }, // react-globe.gl and our sky code must share one copy of three.js
  server: {
    fs: { allow: ['..'] }, // lets the app import ../data/hubs.json
    proxy: { '/v1': 'http://127.0.0.1:8000' }, // estimator + chat service (python -m pipeline.estimator_api)
  },
})
