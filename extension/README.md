# RepoSage Chrome Extension

An extension that injects the **RepoSage AI Assistant** directly onto any repository page on [github.com](https://github.com).

---

## 🌟 What it Does

- **Automatic Repo Detection**: When you browse to any GitHub repo (e.g. `https://github.com/ayushp4219-boop/RepoSage`), the extension detects the repository automatically.
- **Floating 🦉 Button**: An owl badge floats on the bottom-right of your screen.
- **Slide-Out Assistant Sidebar**: Clicking the button opens the RepoSage assistant without leaving your GitHub tab.
- **One-Click Ingestion**: Click **⚡ Index Repo** to parse AST symbols, build call graphs, and embed the codebase locally via your RepoSage backend.
- **Verified Code Citations**: Click citations (e.g., `auth/middleware.py#L9-L26`) to jump straight to GitHub's code view for that exact line range.
- **Quick Queries**: Pre-configured query chips for Architecture, Entry Point, Auth / Security, and Bug Hunting.

---

## 🚀 How to Install & Use in Google Chrome / Brave / Edge

1. **Start the RepoSage Local Backend**:
   ```bash
   # From your RepoSage repository root
   python3 -m reposage.cli serve --port 8000
   ```
   *(Or using your virtual environment: `.venv/bin/python3 -m reposage.cli serve`)*

2. **Load Extension in Chrome**:
   - Open Chrome and navigate to `chrome://extensions/`
   - Enable **Developer mode** (toggle in the top-right corner).
   - Click **Load unpacked** (top-left button).
   - Select the `extension/` folder inside your RepoSage directory:
     ```
     /Users/ayushpgolurajapati/Downloads/RepoSage/extension
     ```

3. **Browse GitHub**:
   - Open any GitHub repository in your browser (e.g., https://github.com/ayushp4219-boop/RepoSage).
   - Click the floating **🦉** button at the bottom-right corner!
   - Index the repository and ask questions directly on GitHub.
