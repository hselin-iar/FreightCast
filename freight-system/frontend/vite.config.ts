import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom')) {
              return 'vendor-react';
            }
            if (id.includes('recharts')) {
              return 'vendor-charts';
            }
            if (id.includes('katex')) {
              return 'vendor-katex';
            }
            if (id.includes('react-simple-maps') || id.includes('d3-geo')) {
              return 'vendor-maps';
            }
          }
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
})
