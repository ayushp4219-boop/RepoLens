import { defineManifest } from '@crxjs/vite-plugin';

export default defineManifest({
  manifest_version: 3,
  name: 'RepoLens',
  version: '0.1.0',
  description: 'Visualize GitHub repository file dependencies and understand change impact.',

  icons: {
    '16': 'icons/icon16.png',
    '32': 'icons/icon32.png',
    '48': 'icons/icon48.png',
    '128': 'icons/icon128.png',
  },

  action: {
    default_icon: {
      '16': 'icons/icon16.png',
      '32': 'icons/icon32.png',
    },
    default_title: 'Open RepoLens',
  },

  side_panel: {
    default_path: 'src/panel/index.html',
  },

  background: {
    service_worker: 'src/background/index.ts',
    type: 'module',
  },

  content_scripts: [
    {
      matches: ['https://github.com/*'],
      js: ['src/content/index.ts'],
      run_at: 'document_idle',
    },
  ],

  options_page: 'src/options/index.html',

  permissions: ['sidePanel', 'storage', 'tabs', 'activeTab'],

  host_permissions: [
    'https://github.com/*',
    'https://api.github.com/*',
    'https://raw.githubusercontent.com/*',
  ],

  optional_host_permissions: ['https://*/*'],
});
