/// <reference types="vite/client" />

/**
 * Vite injects `import.meta.env` at build time. Copy `.env.example` to `.env` locally.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_ORG_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
