# RepoLens

A Chrome side-panel extension that helps developers explore the files likely affected by a proposed repository change.

## Current MVP progress

All eight MVP phases are complete. RepoLens detects public GitHub repositories, fetches and analyzes source files, renders an interactive dependency map, produces local graph-grounded impact reports, and can optionally use a server-side Gemma proxy for richer analysis.

## Load the extension in Chrome

1. Run `npm install` and `npm run build`.
2. Open `chrome://extensions`, enable **Developer mode**, then choose **Load unpacked**.
3. Select this project's `dist` directory.
4. Visit a public GitHub repository, click the RepoLens toolbar icon, and turn off **Demo** in the side panel (or Options) to fetch the repository.

## Optional AI proxy (Vercel)

The extension works without a backend: it falls back to local analysis. To enable AI analysis, deploy this repository to Vercel and configure the server-side environment variables in [.env.example](/Users/ayushpgolurajapati/Downloads/RepoLens/.env.example).

1. Import the repository into Vercel (the `api/impact.ts` serverless endpoint is detected automatically).
2. Set `GEMMA_API_URL` to an OpenAI-compatible endpoint for your chosen Gemma instruct model, plus `GEMMA_API_KEY` and optionally `GEMMA_MODEL`.
3. Deploy, then enter `https://your-deployment.vercel.app/api/impact` in RepoLens **Options** and save.
4. Reload the extension, run an analysis, and grant the one-time request to access that HTTPS proxy. A successful model response is labeled **AI analysis**; an unavailable or malformed response is safely labeled **AI fallback**.

The proxy sends at most 10 locally ranked file summaries, import paths, and dependent paths. It never receives raw repository source. It validates model paths and retries malformed output once before returning a graph-limited fallback. The proxy's in-memory rate limiter is suitable for an MVP; use durable, distributed rate limiting for production.

## End-to-end manual test

1. Open a small public TypeScript or JavaScript repository on GitHub.
2. Open RepoLens and disable Demo Mode. The status indicator should progress from GitHub discovery through file fetching and finish with the fetched file count.
3. Enter a concrete request such as “add authorization middleware” and select **Analyze Local Impact**. If the optional proxy is configured, the same action may return **AI analysis**.
4. Confirm the result contains only files that exist in the Dependency Map and ranks path, export, summary, and graph-neighbor evidence. Disconnect the proxy or provide an invalid response to confirm **AI fallback** works.
5. Open the **Dependency Map** tab after the fetch completes. It should show the repository's real source files and their local import relationships; zoom, pan, and use the minimap to explore it.
6. Filter the map by a filename or directory fragment, then clear the filter to restore the full graph.
7. Click a node (or focus it and press Enter) to open its exact commit-pinned GitHub file in a new tab.
8. Check that extensionless imports, directory `index` imports, `.js` references to TypeScript source, `require()`, dynamic imports, and `tsconfig.json` aliases resolve when their target exists in the repository. External package imports are excluded.
9. Check that only `.ts`, `.tsx`, `.js`, and `.jsx` files are counted; dependencies, build output, declarations, minified files, lockfiles, and files over 200 KB are skipped.
10. Use a repository with more than 150 supported files. If its `/src` directory has 150 or fewer supported files, select **Analyze /src instead**.
11. Try an unavailable/private repository or disconnect from the network. RepoLens should explain the failure and switch to Demo Mode.

## Notes

- GitHub access tokens are optional and stored in `chrome.storage.local`; use the Options page to configure one. Never include a token in a remote URL or source file.
- Cached repository snapshots are keyed by `owner/repo@commit SHA` and include only source paths, sizes, and derived graph summaries—never source-file contents.

## Known limitations

- Public GitHub repositories only; private repositories and local folders are out of scope.
- Analysis is limited to 150 TS/TSX/JS/JSX files and a 200 KB per-file limit. Large repositories can be scoped to `/src` when it fits.
- Import analysis is intentionally lightweight and does not resolve workspace packages, custom bundler aliases, generated modules, or runtime-computed imports.
- The AI proxy accepts an OpenAI-compatible Gemma endpoint; provider-specific authentication or payload conventions may need a small adapter in `api/impact.ts`.
- Vercel's in-memory rate limit does not coordinate across cold starts or multiple serverless instances.
