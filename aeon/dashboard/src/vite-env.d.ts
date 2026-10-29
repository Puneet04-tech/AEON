/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin when the console is hosted separately from the API. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
