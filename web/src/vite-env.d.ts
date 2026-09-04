/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端 API 基址；空串表示同源相对路径。 */
  readonly VITE_API_BASE?: string;
  /** 前端部署子路径（GitHub Pages 项目站点为 /<repo>/）。 */
  readonly VITE_BASE_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
