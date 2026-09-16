// PantryChef AI — frontend logic
// Streams text from the backend and renders it progressively (no full-page
// reload, no waiting for the whole response before showing anything).

const form = document.getElementById("recipe-form");
const generateBtn = document.getElementById("generate-btn");
const formError = document.getElementById("form-error");

const cardEl = document.getElementById("recipe-card");
const emptyStateEl = document.getElementById("card-empty-state");
const contentEl = document.getElementById("card-content");

const chatPanel = document.getElementById("chat-panel");
const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

let currentRecipeRaw = "";        // raw markdown text of the latest recipe
let chatHistory = [];             // [{role, content}, ...]

/** Very small markdown-ish -> HTML renderer, scoped to the shape our
 *  system prompt asks Claude to produce (#, ##, -, 1., paragraphs). */
function renderMarkdownFragment(md) {
  const lines = md.split("\n");
  let html = "";
  let inUl = false, inOl = false;

  const closeLists = () => {
    if (inUl) { html += "</ul>"; inUl = false; }
    if (inOl) { html += "</ol>"; inOl = false; }
  };

  for (let raw of lines) {
    const line = raw.trim();
    if (line === "") { continue; }

    if (line.startsWith("# ")) {
      closeLists();
      html += `<h1>${escapeHtml(line.slice(2))}</h1>`;
    } else if (line.startsWith("## ")) {
      closeLists();
      const heading = line.slice(3);
      if (/chef.?s tip/i.test(heading)) {
        html += `<h2>${escapeHtml(heading)}</h2>`;
      } else {
        html += `<h2>${escapeHtml(heading)}</h2>`;
      }
    } else if (/^[-*]\s+/.test(line)) {
      if (!inUl) { closeLists(); html += "<ul>"; inUl = true; }
      html += `<li>${escapeHtml(line.replace(/^[-*]\s+/, ""))}</li>`;
    } else if (/^\d+\.\s+/.test(line)) {
      if (!inOl) { closeLists(); html += "<ol>"; inOl = true; }
      html += `<li>${escapeHtml(line.replace(/^\d+\.\s+/, ""))}</li>`;
    } else {
      closeLists();
      html += `<p>${escapeHtml(line)}</p>`;
    }
  }
  closeLists();
  return html;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function setLoading(isLoading) {
  generateBtn.disabled = isLoading;
  generateBtn.classList.toggle("is-loading", isLoading);
}

async function streamToTarget(response, onChunk) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let full = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onChunk(full, chunk);
  }
  return full;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;

  const ingredients = document.getElementById("ingredients").value.trim();
  const dietary = document.getElementById("dietary").value.trim();
  const cuisine = document.getElementById("cuisine").value.trim();
  const servings = Number(document.getElementById("servings").value) || 2;

  if (!ingredients) {
    formError.textContent = "Please list at least one ingredient.";
    formError.hidden = false;
    return;
  }

  setLoading(true);
  emptyStateEl.hidden = true;
  contentEl.hidden = false;
  contentEl.innerHTML = `<span class="cursor-blink"></span>`;
  chatPanel.hidden = true;
  chatLog.innerHTML = "";
  chatHistory = [];
  currentRecipeRaw = "";

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ingredients, dietary, cuisine, servings }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed (${res.status})`);
    }

    const full = await streamToTarget(res, (fullText) => {
      currentRecipeRaw = fullText;
      contentEl.innerHTML = renderMarkdownFragment(fullText) + `<span class="cursor-blink"></span>`;
      contentEl.scrollTop = contentEl.scrollHeight;
    });

    currentRecipeRaw = full;
    contentEl.innerHTML = renderMarkdownFragment(full);
    chatPanel.hidden = false;
  } catch (err) {
    contentEl.innerHTML = `<p style="color:#B5502D;">Couldn't generate a recipe: ${escapeHtml(err.message)}</p>`;
  } finally {
    setLoading(false);
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  chatHistory.push({ role: "user", content: text });
  appendChatBubble("user", text);
  chatInput.value = "";
  chatInput.disabled = true;

  const assistantBubble = appendChatBubble("assistant", "");
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: chatHistory,
        recipe_context: currentRecipeRaw,
      }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed (${res.status})`);
    }

    const full = await streamToTarget(res, (fullText) => {
      assistantBubble.textContent = fullText;
      chatLog.scrollTop = chatLog.scrollHeight;
    });
    chatHistory.push({ role: "assistant", content: full });
  } catch (err) {
    assistantBubble.textContent = `Couldn't reach Chef Nova: ${err.message}`;
  } finally {
    chatInput.disabled = false;
    chatInput.focus();
  }
});

function appendChatBubble(role, text) {
  const el = document.createElement("div");
  el.className = `chat-msg chat-msg--${role}`;
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}
