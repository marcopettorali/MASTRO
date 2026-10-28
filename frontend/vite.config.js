import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
// Development port of the MASTRO interface.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, strictPort: true },
})
