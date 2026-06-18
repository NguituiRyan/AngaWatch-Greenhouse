/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin; defaults to http://localhost:8000. Base path is `/api/v1`. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
