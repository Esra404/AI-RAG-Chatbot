const state = { chats: [], currentChat: null, documents: [], sending: false, sourceLookup: {}, webSearch: false, webSearchReady: false };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body = {};
  try { body = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(body.detail || "İşlem tamamlanamadı.");
  return body;
}

function toast(text, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.textContent = text;
  $("#toast-stack").append(node);
  setTimeout(() => node.remove(), 3600);
}

function escapeHtml(value = "") {
  const div = document.createElement("div"); div.textContent = value; return div.innerHTML;
}

function formatMarkdownSegment(value = "") {
  return escapeHtml(value)
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__([\s\S]+?)__/g, "<strong>$1</strong>");
}

function contentWithSourceLinks(message, messageKey) {
  const sources = message.sources || [];
  const webSources = message.web_sources || [];
  return String(message.content || "").split(/(\[Kaynak\s+\d+\]|\[Web\s+\d+\])/gi).map(part => {
    const documentMatch = part.match(/^\[Kaynak\s+(\d+)\]$/i);
    if (documentMatch) {
      const number = Number(documentMatch[1]);
      const source = sources.find(item => Number(item.number) === number) || sources[number - 1];
      if (!source?.chunk) return escapeHtml(part);
      return `<button class="source-ref" data-source-message="${messageKey}" data-source-number="${number}" title="Kullanılan bölümü göster">[Kaynak ${number}]</button>`;
    }
    const webMatch = part.match(/^\[Web\s+(\d+)\]$/i);
    if (webMatch) {
      const number = Number(webMatch[1]);
      const source = webSources.find(item => Number(item.number) === number) || webSources[number - 1];
      if (!source?.url) return escapeHtml(part);
      return `<a class="source-ref web-ref" href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(source.title)} — siteyi aç"><span>[Web ${number}]</span><em>${escapeHtml(source.title)}</em><b>↗</b></a>`;
    }
    return formatMarkdownSegment(part);
  }).join("");
}

function openSource(messageKey, number) {
  const sources = state.sourceLookup[messageKey] || [];
  const source = sources.find(item => Number(item.number) === number) || sources[number - 1];
  if (!source?.chunk) { toast("Bu eski mesaj için kaynak metni kaydedilmemiş.", true); return; }
  $("#source-modal-label").textContent = `KAYNAK ${number}`;
  $("#source-modal-title").textContent = source.document_name;
  $("#source-modal-meta").innerHTML = `<span>Belge bölümü ${(source.chunk_position ?? 0) + 1}</span><span>Benzerlik ${Number(source.score || 0).toFixed(4)}</span>`;
  $("#source-modal-text").textContent = source.chunk;
  $("#source-modal").classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeSource() {
  $("#source-modal").classList.add("hidden");
  document.body.style.overflow = "";
}

async function loadStatus() {
  const status = await api("/api/status");
  $("#api-status").textContent = status.ready ? "OpenAI anahtarı hazır" : "API anahtarı gerekli";
  $("#status-dot").classList.toggle("online", status.ready);
  $("#model-name").textContent = status.model.replace("gpt-", "GPT-").replaceAll("-", " ");
  state.webSearchReady = Boolean(status.web_search_ready);
  $("#web-toggle").disabled = !state.webSearchReady;
  if (!state.webSearchReady) $("#web-toggle").title = "Tavily API anahtarı gerekli";
}

async function loadChats(selectFirst = true) {
  state.chats = await api("/api/chats");
  renderChats();
  if (selectFirst && !state.currentChat && state.chats.length) await selectChat(state.chats[0].id);
}

function renderChats() {
  $("#chat-count").textContent = state.chats.length;
  $("#chat-list").innerHTML = state.chats.map(chat => `
    <div class="chat-item ${state.currentChat?.id === chat.id ? "active" : ""}" data-chat="${chat.id}">
      ${escapeHtml(chat.title)}<button class="chat-delete" data-delete="${chat.id}" title="Sil">×</button>
    </div>`).join("") || '<div class="empty-docs">Henüz sohbet yok.<br>Yeni bir sohbet başlatın.</div>';
  document.querySelectorAll("[data-chat]").forEach(node => node.onclick = e => {
    if (!e.target.dataset.delete) selectChat(node.dataset.chat);
  });
  document.querySelectorAll("[data-delete]").forEach(node => node.onclick = e => { e.stopPropagation(); deleteChat(node.dataset.delete); });
}

async function createChat() {
  const chat = await api("/api/chats", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({title:"Yeni sohbet"}) });
  state.chats.unshift(chat); await selectChat(chat.id); renderChats(); $("#message-input").focus();
}

async function selectChat(id) {
  state.currentChat = await api(`/api/chats/${id}`);
  $("#chat-title").textContent = state.currentChat.title;
  renderMessages(state.currentChat.messages); renderChats();
}

async function deleteChat(id) {
  await api(`/api/chats/${id}`, {method:"DELETE"});
  if (state.currentChat?.id === id) state.currentChat = null;
  await loadChats(false);
  if (!state.currentChat && state.chats.length) await selectChat(state.chats[0].id);
  if (!state.chats.length) { $("#chat-title").textContent = "Yeni sohbet"; renderMessages([]); }
}

function renderMessages(messages = []) {
  state.sourceLookup = {};
  if (!messages.length) {
    $("#messages").innerHTML = `<div class="welcome" id="welcome"><div class="orb"><span>✦</span></div><h2>Belgelerinizle konuşun.</h2><p>Sağ panelden belgelerinizi ekleyin, kullanmak istediklerinizi aktif edin ve sorularınızı sorun.</p><div class="suggestions"><button>Aktif belgeleri özetle</button><button>Önemli noktaları listele</button><button>Belgeler arasında karşılaştırma yap</button></div></div>`;
    bindSuggestions(); return;
  }
  $("#messages").innerHTML = messages.map(messageHtml).join(""); scrollMessages();
}

function messageHtml(message) {
  const messageKey = message.id || `temporary-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const messageSources = message.sources || [];
  const webSources = message.web_sources || [];
  const webQueries = message.web_queries || (message.web_query ? [message.web_query] : []);
  state.sourceLookup[messageKey] = messageSources;
  const grouped = new Map();
  messageSources.forEach(source => grouped.set(source.document_id, {
    name: source.document_name,
    count: (grouped.get(source.document_id)?.count || 0) + 1,
  }));
  const sourceSummary = [...grouped.values()].map(source =>
    `<span class="source-chip">${escapeHtml(source.name)} • ${source.count} bölüm</span>`
  ).join("");
  const webSummary = webSources.map(source =>
    `<a class="source-chip web-chip" href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer" title="Siteyi aç"><span>↗</span>${escapeHtml(source.title)}</a>`
  ).join("");
  const querySummary = webQueries.map(query =>
    `<span class="web-query-chip" title="Tavily arama sorgusu"><b>⌕</b> ${escapeHtml(query)}</span>`
  ).join("");
  const content = message.role === "assistant" ? contentWithSourceLinks(message, messageKey) : escapeHtml(message.content);
  const summaries = sourceSummary + webSummary;
  return `<article class="message ${message.role}"><span class="avatar">${message.role === "user" ? "S" : "✦"}</span><div class="bubble">${content}${querySummary ? `<div class="web-queries">${querySummary}</div>` : ""}${summaries ? `<div class="sources">${summaries}</div>` : ""}</div></article>`;
}

function addTyping() {
  $("#messages").insertAdjacentHTML("beforeend", '<article class="message assistant" id="typing"><span class="avatar">✦</span><div class="bubble typing"><i></i><i></i><i></i></div></article>'); scrollMessages();
}

function scrollMessages() { const box = $("#messages"); requestAnimationFrame(() => box.scrollTop = box.scrollHeight); }

async function sendMessage(prefill) {
  const input = $("#message-input"); const content = (prefill || input.value).trim();
  if (!content || state.sending) return;
  if (!state.currentChat) await createChat();
  state.sending = true; $("#send-button").disabled = true;
  let optimisticMessage = null;
  try {
    if (!state.currentChat.messages.length) $("#messages").innerHTML = "";
    $("#messages").insertAdjacentHTML("beforeend", messageHtml({role:"user", content}));
    optimisticMessage = $("#messages").lastElementChild;
    input.value = ""; resizeInput(); addTyping();
    const result = await api(`/api/chats/${state.currentChat.id}/messages`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({content, web_search:state.webSearch})});
    $("#typing")?.remove(); $("#messages").insertAdjacentHTML("beforeend", messageHtml(result.assistant));
    state.currentChat.messages.push(result.user, result.assistant); await loadChats(false);
    const latest = state.chats.find(c => c.id === state.currentChat.id); if (latest) { state.currentChat.title = latest.title; $("#chat-title").textContent = latest.title; }
  } catch (error) { $("#typing")?.remove(); optimisticMessage?.remove(); if (!input.value) { input.value = content; resizeInput(); } toast(error.message, true); }
  finally { state.sending = false; $("#send-button").disabled = false; input.focus(); scrollMessages(); }
}

async function loadDocuments() {
  state.documents = await api("/api/documents"); renderDocuments();
}

function renderDocuments() {
  const active = state.documents.filter(doc => doc.active).length;
  $("#doc-count").textContent = state.documents.length; $("#active-count").textContent = `${active} aktif`;
  $("#document-list").innerHTML = state.documents.map(doc => {
    const ext = doc.name.split(".").pop().toUpperCase();
    return `<div class="document-card ${doc.active ? "active" : ""}"><span class="doc-icon">${escapeHtml(ext)}</span><div class="doc-info"><strong title="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}</strong><small>${doc.chunk_count} parça • ${doc.active ? "Aktif" : "Pasif"}</small></div><button class="toggle ${doc.active ? "active" : ""}" data-toggle="${doc.id}" aria-label="Durumu değiştir"></button></div>`;
  }).join("") || '<div class="empty-docs">Kütüphaneniz boş.<br>İlk dokümanınızı yükleyin.</div>';
  document.querySelectorAll("[data-toggle]").forEach(button => button.onclick = () => toggleDocument(button.dataset.toggle));
}

async function toggleDocument(id) {
  const updated = await api(`/api/documents/${id}/toggle`, {method:"PATCH"});
  const index = state.documents.findIndex(doc => doc.id === id); state.documents[index] = updated; renderDocuments();
}

async function uploadFile(file) {
  if (!file) return;
  $("#upload-progress").classList.remove("hidden");
  const form = new FormData(); form.append("file", file);
  try {
    const result = await api("/api/documents", {method:"POST", body:form});
    toast(result.duplicate ? "Bu belge daha önce işlendi; mevcut indeks kullanıldı." : "Belge embedlendi ve aktif edildi.");
    await loadDocuments();
  } catch (error) { toast(error.message, true); }
  finally { $("#upload-progress").classList.add("hidden"); $("#file-input").value = ""; }
}

function resizeInput() { const input = $("#message-input"); input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
function bindSuggestions() { document.querySelectorAll(".suggestions button").forEach(button => button.onclick = () => sendMessage(button.textContent)); }

$("#new-chat").onclick = createChat;
$("#send-button").onclick = () => sendMessage();
$("#web-toggle").onclick = () => {
  if (!state.webSearchReady) { toast("Tavily API anahtarı yapılandırılmamış.", true); return; }
  state.webSearch = !state.webSearch;
  $("#web-toggle").classList.toggle("active", state.webSearch);
  $("#web-toggle").setAttribute("aria-pressed", String(state.webSearch));
  $("#web-toggle").title = state.webSearch ? "Web araması açık" : "Web araması kapalı";
};
$("#message-input").oninput = resizeInput;
$("#message-input").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
$("#file-input").onchange = e => uploadFile(e.target.files[0]);
$("#messages").onclick = e => {
  const reference = e.target.closest(".source-ref");
  if (reference) openSource(reference.dataset.sourceMessage, Number(reference.dataset.sourceNumber));
};
document.querySelectorAll("[data-close-source]").forEach(node => node.onclick = closeSource);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSource(); });
const zone = $("#upload-zone");
zone.ondragover = e => { e.preventDefault(); zone.classList.add("drag"); };
zone.ondragleave = () => zone.classList.remove("drag");
zone.ondrop = e => { e.preventDefault(); zone.classList.remove("drag"); uploadFile(e.dataTransfer.files[0]); };

Promise.all([loadStatus(), loadChats(), loadDocuments()]).catch(error => toast(error.message, true));
bindSuggestions();
