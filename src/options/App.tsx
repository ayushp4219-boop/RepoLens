import { useEffect, useState } from 'react';
import { Network, Eye, EyeOff, Save } from 'lucide-react';

interface Settings {
  githubToken: string;
  demoMode: boolean;
  proxyUrl: string;
}

const DEFAULT_SETTINGS: Settings = {
  githubToken: '',
  demoMode: false,
  proxyUrl: '',
};

export default function OptionsApp() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);
  const [showToken, setShowToken] = useState(false);

  useEffect(() => {
    chrome.storage.local.get(['githubToken', 'demoMode', 'proxyUrl'], (result) => {
      setSettings({
        githubToken: (result.githubToken as string) || '',
        demoMode: (result.demoMode as boolean) || false,
        proxyUrl: (result.proxyUrl as string) || '',
      });
    });
  }, []);

  const handleSave = () => {
    chrome.storage.local.set(settings, () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  };

  return (
    <div className="min-h-screen bg-[#0d1117] text-[#e6edf3] p-8">
      <div className="max-w-lg mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center gap-3">
          <Network className="w-6 h-6 text-[#58a6ff]" />
          <div>
            <h1 className="text-lg font-semibold">RepoLens Options</h1>
            <p className="text-xs text-[#8b949e]">Configure your RepoLens experience</p>
          </div>
        </div>

        {/* GitHub Token */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider">
            GitHub Access
          </h2>
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4 space-y-3">
            <div>
              <label className="text-sm font-medium text-[#e6edf3]">
                Personal Access Token
              </label>
              <p className="text-xs text-[#8b949e] mt-0.5">
                Optional. Increases the GitHub API rate limit from 60 to 5000 requests/hour.
                Requires <code className="text-[#58a6ff]">repo:read</code> scope (or public_repo for public repos only).
              </p>
            </div>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={settings.githubToken}
                onChange={(e) => setSettings((s) => ({ ...s, githubToken: e.target.value }))}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-3 py-2 pr-9 text-sm text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] transition-colors"
              />
              <button
                onClick={() => setShowToken((s) => !s)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8b949e] hover:text-[#e6edf3]"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </section>

        {/* Proxy URL */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider">
            Backend Proxy
          </h2>
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4 space-y-3">
            <div>
              <label className="text-sm font-medium text-[#e6edf3]">Proxy URL</label>
              <p className="text-xs text-[#8b949e] mt-0.5">
                URL of your deployed AI proxy (Vercel function). Leave blank to use Demo Mode.
              </p>
            </div>
            <input
              type="url"
              value={settings.proxyUrl}
              onChange={(e) => setSettings((s) => ({ ...s, proxyUrl: e.target.value }))}
              placeholder="https://your-proxy.vercel.app/api/impact"
              className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-3 py-2 text-sm text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] transition-colors"
            />
          </div>
        </section>

        {/* Demo Mode */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-[#8b949e] uppercase tracking-wider">
            Demo Mode
          </h2>
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <div className="relative mt-0.5">
                <input
                  type="checkbox"
                  checked={settings.demoMode}
                  onChange={(e) => setSettings((s) => ({ ...s, demoMode: e.target.checked }))}
                  className="sr-only"
                />
                <div
                  className={[
                    'w-9 h-5 rounded-full transition-colors',
                    settings.demoMode ? 'bg-[#238636]' : 'bg-[#30363d]',
                  ].join(' ')}
                >
                  <div
                    className={[
                      'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform',
                      settings.demoMode ? 'translate-x-4' : 'translate-x-0',
                    ].join(' ')}
                  />
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-[#e6edf3]">Enable Demo Mode</p>
                <p className="text-xs text-[#8b949e] mt-0.5">
                  Use built-in mock data instead of fetching from GitHub. Works offline with no API key.
                  Auto-enables if GitHub fetching fails.
                </p>
              </div>
            </label>
          </div>
        </section>

        {/* Save */}
        <button
          onClick={handleSave}
          className="flex items-center gap-2 bg-[#238636] hover:bg-[#2ea043] text-white text-sm font-medium px-4 py-2 rounded-md transition-colors"
        >
          <Save className="w-4 h-4" />
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
