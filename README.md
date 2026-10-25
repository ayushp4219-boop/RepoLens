# RepoLens

A Chrome side-panel extension that helps developers explore the files likely affected by a proposed repository change.

## Current MVP progress

Phases 1–5 are complete: the extension detects public GitHub repositories, provides a polished offline Demo Mode, fetches and analyzes public repository source files, and renders an interactive dependency map. AI impact analysis follows in later phases.

## Load the extension in Chrome

1. Run `npm install` and `npm run build`.
2. Open `chrome://extensions`, enable **Developer mode**, then choose **Load unpacked**.
3. Select this project's `dist` directory.
4. Visit a public GitHub repository, click the RepoLens toolbar icon, and turn off **Demo** in the side panel (or Options) to fetch the repository.

## Phase 5 manual test

1. Open a small public TypeScript or JavaScript repository on GitHub.
2. Open RepoLens and disable Demo Mode. The status indicator should progress from GitHub discovery through file fetching and finish with the fetched file count.
3. Open the **Dependency Map** tab after the fetch completes. It should show the repository's real source files and their local import relationships; zoom, pan, and use the minimap to explore it.
4. Filter the map by a filename or directory fragment, then clear the filter to restore the full graph.
5. Click a node (or focus it and press Enter) to open its exact commit-pinned GitHub file in a new tab.
6. Check that extensionless imports, directory `index` imports, `.js` references to TypeScript source, `require()`, dynamic imports, and `tsconfig.json` aliases resolve when their target exists in the repository. External package imports are excluded.
7. Check that only `.ts`, `.tsx`, `.js`, and `.jsx` files are counted; dependencies, build output, declarations, minified files, lockfiles, and files over 200 KB are skipped.
8. Use a repository with more than 150 supported files. If its `/src` directory has 150 or fewer supported files, select **Analyze /src instead**.
9. Try an unavailable/private repository or disconnect from the network. RepoLens should explain the failure and switch to Demo Mode.

## Notes

- GitHub access tokens are optional and stored in `chrome.storage.local`; use the Options page to configure one. Never include a token in a remote URL or source file.
- Cached repository snapshots are keyed by `owner/repo@commit SHA` and include only source paths, sizes, and derived graph summaries—never source-file contents.
