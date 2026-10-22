// RepoSage GitHub Injected Content Script

(function () {
  if (window.__reposage_injected) return;
  window.__reposage_injected = true;

  const DEFAULT_BACKEND_URL = "http://localhost:8000";
  let backendUrl = DEFAULT_BACKEND_URL;
  let isOpen = false;
  let isIndexing = false;
  let isAsking = false;

  // Extract current owner & repo from GitHub pathname: /<owner>/<repo>
  function getRepoInfo() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts.length >= 2) {
      const owner = parts[0];
      const repo = parts[1];
      // Exclude special GitHub sub-paths like settings, notifications, pull-requests root, etc.
      const excluded = ["settings", "notifications", "explore", "marketplace", "organizations"];
      if (!excluded.includes(owner)) {
        return {
          owner,
          repo,
          fullName: `${owner}/${repo}`,
          url: `https://github.com/${owner}/${repo}.git`
        };
      }
    }
    return null;
  }

  const repoInfo = getRepoInfo();
  if (!repoInfo) {
    // Not on a repository page
    return;
  }

  // 1. Create Floating Button
  const toggleBtn = document.createElement("div");
  toggleBtn.id = "reposage-toggle-btn";
  toggleBtn.title = `Open RepoSage for ${repoInfo.fullName}`;
  toggleBtn.innerHTML = `
    <span>🦉</span>
    <span id="reposage-toggle-badge">AI</span>
  `;
  document.body.appendChild(toggleBtn);

  // 2. Create Sidebar Container
  const sidebar = document.createElement("div");
  sidebar.id = "reposage-sidebar";
  sidebar.innerHTML = `
    <div class="reposage-header">
      <div class="reposage-logo">🦉</div>
      <div class="reposage-header-title">RepoSage AI Assistant</div>
      <div class="reposage-header-actions">
        <button class="reposage-icon-btn" id="reposage-clear-btn" title="Clear chat">↺</button>
        <button class="reposage-icon-btn" id="reposage-close-btn" title="Close sidebar">✕</button>
      </div>
    </div>

    <div class="reposage-repo-bar">
      <div class="reposage-repo-info">
        <span class="reposage-repo-name" title="${repoInfo.fullName}">📦 ${repoInfo.fullName}</span>
        <button class="reposage-index-btn" id="reposage-index-btn">⚡ Index Repo</button>
      </div>
      <div class="reposage-status-line">
        <span class="reposage-status-dot" id="reposage-status-dot"></span>
        <span id="reposage-status-text">Checking RepoSage server (localhost:8000)...</span>
      </div>
    </div>

    <div class="reposage-chips">
      <div class="reposage-chip" data-q="Explain the architecture of this repository">🏛️ Architecture</div>
      <div class="reposage-chip" data-q="What is the main entry point and how does it execute?">🚀 Entry Point</div>
      <div class="reposage-chip" data-q="Where are authentication, tokens, or security handled?">🔒 Auth / Security</div>
      <div class="reposage-chip" data-q="Are there any known bugs or edge cases in the logic?">🐞 Find Bugs</div>
    </div>

    <div class="reposage-messages" id="reposage-messages">
      <div class="reposage-msg ai">
        <div class="reposage-bubble">
          👋 Hi! I'm <strong>RepoSage</strong> 🦉 — your local-first code intelligence assistant.<br><br>
          I provide <strong>grounded answers</strong> with exact source code file & line citations for <code>${repoInfo.fullName}</code>.
        </div>
        <div class="reposage-meta">RepoSage · Ready</div>
      </div>
    </div>

    <div class="reposage-footer">
      <div class="reposage-input-box">
        <textarea class="reposage-textarea" id="reposage-input" placeholder="Ask anything about ${repoInfo.repo}... (Shift+Enter = newline)" rows="1"></textarea>
        <div class="reposage-input-actions">
          <span class="reposage-input-hint">Shift+Enter for newline</span>
          <button class="reposage-send-btn" id="reposage-send-btn" title="Send message">➤</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(sidebar);

  // References
  const closeBtn = sidebar.querySelector("#reposage-close-btn");
  const clearBtn = sidebar.querySelector("#reposage-clear-btn");
  const indexBtn = sidebar.querySelector("#reposage-index-btn");
  const statusDot = sidebar.querySelector("#reposage-status-dot");
  const statusText = sidebar.querySelector("#reposage-status-text");
  const messagesBox = sidebar.querySelector("#reposage-messages");
  const chatInput = sidebar.querySelector("#reposage-input");
  const sendBtn = sidebar.querySelector("#reposage-send-btn");
  const chips = sidebar.querySelectorAll(".reposage-chip");

  // Toggle Sidebar
  function setSidebarOpen(open) {
    isOpen = open;
    if (isOpen) {
      sidebar.classList.add("open");
      toggleBtn.style.display = "none";
      chatInput.focus();
      checkServerHealth();
    } else {
      sidebar.classList.remove("open");
      toggleBtn.style.display = "flex";
    }
  }

  toggleBtn.addEventListener("click", () => setSidebarOpen(true));
  closeBtn.addEventListener("click", () => setSidebarOpen(false));

  // Quick Chips
  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      const query = chip.getAttribute("data-q");
      if (query) {
        chatInput.value = query;
        submitQuery();
      }
    });
  });

  // Clear Chat
  clearBtn.addEventListener("click", () => {
    messagesBox.innerHTML = `
      <div class="reposage-msg ai">
        <div class="reposage-bubble">
          Chat cleared. Ask anything about <strong>${repoInfo.fullName}</strong>!
        </div>
      </div>
    `;
  });

  // Auto-resize textarea
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuery();
    }
  });

  sendBtn.addEventListener("click", submitQuery);

  // Check backend server connection
  async function checkServerHealth() {
    try {
      const res = await fetch(`${backendUrl}/health`);
      if (res.ok) {
        statusDot.className = "reposage-status-dot ready";
        statusText.textContent = "RepoSage Backend Online (localhost:8000)";
        return true;
      }
    } catch (e) {
      statusDot.className = "reposage-status-dot error";
      statusText.innerHTML = `Backend offline. Run: <code style="color:#cad3f5;">reposage serve</code>`;
    }
    return false;
  }

  // Index Repo Action
  indexBtn.addEventListener("click", async () => {
    if (isIndexing) return;
    isIndexing = true;
    indexBtn.disabled = true;
    indexBtn.textContent = "⏳ Indexing...";
    statusDot.className = "reposage-status-dot indexing";
    statusText.textContent = `Indexing ${repoInfo.fullName}...`;

    appendMessage("ai", `🔄 Ingesting and building symbol graph for <code>${repoInfo.url}</code>...`);

    try {
      const res = await fetch(`${backendUrl}/index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url_or_path: repoInfo.url })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || "Indexing failed");

      statusDot.className = "reposage-status-dot ready";
      statusText.textContent = `Indexed (Repo ID: ${data.repo_id})`;
      indexBtn.textContent = "✓ Indexed";
      appendMessage("ai", `✅ <strong>${repoInfo.fullName}</strong> indexed successfully! You can now ask questions.`);
    } catch (err) {
      statusDot.className = "reposage-status-dot error";
      statusText.textContent = `Indexing failed: ${err.message}`;
      indexBtn.textContent = "⚡ Retry Index";
      appendMessage("ai", `❌ Could not index: ${err.message}. Ensure RepoSage server is running on <code>localhost:8000</code>.`);
    } finally {
      isIndexing = false;
      indexBtn.disabled = false;
    }
  });

  // Submit Query Action
  async function submitQuery() {
    const q = chatInput.value.trim();
    if (!q || isAsking) return;

    appendMessage("user", q);
    chatInput.value = "";
    chatInput.style.height = "auto";
    isAsking = true;
    sendBtn.disabled = true;

    const thinkingId = appendThinking();

    try {
      const res = await fetch(`${backendUrl}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_url_or_path: repoInfo.url,
          question: q
        })
      });
      const data = await res.json();
      removeThinking(thinkingId);

      if (!res.ok) {
        throw new Error(data.error || data.detail || "Request failed");
      }

      appendAIResponse(data);
    } catch (err) {
      removeThinking(thinkingId);
      appendMessage("ai", `❌ Error: ${err.message}. Make sure the RepoSage server is running on <code>http://localhost:8000</code>.`);
    } finally {
      isAsking = false;
      sendBtn.disabled = false;
    }
  }

  function appendMessage(role, html) {
    const wrap = document.createElement("div");
    wrap.className = `reposage-msg ${role}`;
    wrap.innerHTML = `
      <div class="reposage-bubble">${html}</div>
      <div class="reposage-meta">${role === "user" ? "You" : "RepoSage"} · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
    `;
    messagesBox.appendChild(wrap);
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  function appendThinking() {
    const id = "think-" + Date.now();
    const wrap = document.createElement("div");
    wrap.className = "reposage-msg ai";
    wrap.id = id;
    wrap.innerHTML = `
      <div class="reposage-bubble" style="color:var(--reposage-text-dim);font-style:italic;">
        🔍 Searching codebase symbols & call graph...
      </div>
    `;
    messagesBox.appendChild(wrap);
    messagesBox.scrollTop = messagesBox.scrollHeight;
    return id;
  }

  function removeThinking(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function appendAIResponse(data) {
    const wrap = document.createElement("div");
    wrap.className = "reposage-msg ai";

    const tagClass = {
      "bug-hunt": "tag-bug",
      "explain-file": "tag-exp",
      "connection": "tag-con",
      "general": "tag-gen"
    }[data.mode] || "tag-gen";

    let sourcesHtml = "";
    if (data.sources && data.sources.length > 0) {
      sourcesHtml = `
        <div class="reposage-sources">
          <div class="reposage-sources-title">Verified Citations:</div>
          ${data.sources.map(s => {
            const lineRange = `L${s.start_line}-L${s.end_line}`;
            const targetUrl = s.permalink || `https://github.com/${repoInfo.fullName}/blob/main/${s.file_path}#${lineRange}`;
            return `<a class="reposage-citation-link" href="${targetUrl}" target="_blank">📄 ${s.file_path}#${lineRange}</a>`;
          }).join("")}
        </div>
      `;
    }

    const formattedAnswer = formatMarkdown(data.answer);

    wrap.innerHTML = `
      <div class="reposage-bubble">
        <span class="reposage-mode-tag ${tagClass}">● ${data.mode || "Answer"}</span><br>
        ${formattedAnswer}
        ${sourcesHtml}
      </div>
      <div class="reposage-meta">RepoSage · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
    `;
    messagesBox.appendChild(wrap);
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  function formatMarkdown(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/```([a-z]*)\n([\s\S]*?)```/g, "<pre><code>$2</code></pre>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
  }

  // Initial health check in background
  checkServerHealth();
})();
