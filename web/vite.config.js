import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
    const local = mode === 'robot-local'
    const proxy = local ? {
        '/robot': { target: 'http://127.0.0.1:8000', timeout: 0, proxyTimeout: 0 },
    } : { '/api': 'http://localhost:8080' }
    return {
        plugins: [react()],
        build: { outDir: local ? 'dist-local' : 'dist' },
        server: { host: local ? '127.0.0.1' : undefined, proxy },
        preview: { host: local ? '127.0.0.1' : undefined, proxy },
    }
})
