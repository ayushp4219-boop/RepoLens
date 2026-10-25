# RepoLens

A Chrome side-panel extension that helps developers explore the files likely affected by a proposed repository change.

## Current MVP progress

Phases 1–3 are complete: the extension detects public GitHub repositories, provides a polished offline Demo Mode, and fetches a public repository's supported source-file inventory with live progress. Import parsing, dependency graph construction for real repositories, and AI impact analysis follow in later phases.

## Load the extension in Chrome

1. Run `npm install` and `npm run build`.
2. Open `chrome://extensions`, enable **Developer mode**, then choose **Load unpacked**.
3. Select this project's `dist` directory.
4. Visit a public GitHub repository, click the RepoLens toolbar icon, and turn off **Demo** in the side panel (or Options) to fetch the repository.

## Phase 3 manual test

1. Open a small public TypeScript or JavaScript repository on GitHub.
2. Open RepoLens and disable Demo Mode. The status indicator should progress from GitHub discovery through file fetching and finish with the fetched file count.
3. Check that only `.ts`, `.tsx`, `.js`, and `.jsx` files are counted; dependencies, build output, declarations, minified files, lockfiles, and files over 200 KB are skipped.
4. Use a repository with more than 150 supported files. If its `/src` directory has 150 or fewer supported files, select **Analyze /src instead**.
5. Try an unavailable/private repository or disconnect from the network. RepoLens should explain the failure and switch to Demo Mode.

## Notes

- GitHub access tokens are optional and stored in `chrome.storage.local`; use the Options page to configure one. Never include a token in a remote URL or source file.
- Cached repository snapshots are keyed by `owner/repo@commit SHA` and include only source paths and sizes—never source-file contents.
