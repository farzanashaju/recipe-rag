const form = document.getElementById("chat-form");
const textarea = document.getElementById("message");
const messages = document.getElementById("messages");
const sendBtn = document.getElementById("send");
let loadingBubble = null;
let chatHistory = [];

const newChatBtn = document.getElementById("new-chat-btn");
if (newChatBtn) {
  newChatBtn.addEventListener("click", () => {
    chatHistory = [];
    messages.innerHTML = '<article class="msg bot welcome"><p>Share ingredients or your cooking goal.</p></article>';
  });
}
const imageInput = document.getElementById("imageInput");
const imageLabel = document.getElementById("imageLabel");
const imagePreviewContainer = document.getElementById("imagePreviewContainer");
const imagePreview = document.getElementById("imagePreview");
const removeImageBtn = document.getElementById("removeImageBtn");

let currentImageB64 = null;

imageInput.addEventListener("change", async () => {
  if (imageInput.files.length > 0) {
    imageLabel.classList.add("has-file");
    currentImageB64 = await getBase64(imageInput.files[0]);
    imagePreview.src = `data:image/jpeg;base64,${currentImageB64}`;
    imagePreviewContainer.style.display = "block";
    textarea.removeAttribute("required");
  } else {
    clearImage();
  }
});

removeImageBtn.addEventListener("click", () => {
  clearImage();
});

function clearImage() {
  imageInput.value = "";
  currentImageB64 = null;
  imageLabel.classList.remove("has-file");
  imagePreviewContainer.style.display = "none";
  imagePreview.src = "";
  textarea.setAttribute("required", "required");
}

function autoResize() {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
}

function addMessage(text, role, imageBase64 = null) {
  const article = document.createElement("article");
  article.className = `msg ${role}`;

  if (imageBase64 && role === "user") {
    const img = document.createElement("img");
    img.src = `data:image/jpeg;base64,${imageBase64}`;
    img.alt = "User uploaded image";
    article.appendChild(img);
  }

  if (role === "bot" && typeof marked !== "undefined") {
    const content = document.createElement("div");
    content.className = "markdown-body";
    content.innerHTML = marked.parse(text);
    article.appendChild(content);
  } else {
    const p = document.createElement("p");
    p.textContent = text;
    article.appendChild(p);
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
}

function showLoading() {
  if (loadingBubble) {
    return;
  }

  const article = document.createElement("article");
  article.className = "msg bot";
  article.id = "loading-bubble";

  const wrapper = document.createElement("div");
  wrapper.className = "typing";
  wrapper.innerHTML = "<span></span><span></span><span></span>";

  article.appendChild(wrapper);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  loadingBubble = article;
}

function hideLoading() {
  if (!loadingBubble) {
    return;
  }

  loadingBubble.remove();
  loadingBubble = null;
}

async function getBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = error => reject(error);
  });
}

async function sendMessage(message, imageBase64) {
  sendBtn.disabled = true;
  textarea.disabled = true;
  const imageInput = document.getElementById("imageInput");
  imageInput.disabled = true;
  showLoading();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, image: imageBase64, history: chatHistory.slice(0, -1) }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed");
    }

    hideLoading();

    const cleanedAnswer = (payload.answer || "No answer returned.").trim();
    
    addMessage(cleanedAnswer, "bot");
    
    if (payload.answer) {
      chatHistory.push({ role: "assistant", content: cleanedAnswer });
    }

  } catch (error) {
    hideLoading();
    addMessage(`Error: ${error.message}`, "bot");
  } finally {
    sendBtn.disabled = false;
    textarea.disabled = false;
    imageInput.disabled = false;
    clearImage();
    textarea.focus();
  }
}

textarea.addEventListener("input", autoResize);

textarea.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = textarea.value.trim();
  
  if (!message && !currentImageB64) {
    return;
  }

  const imageToSend = currentImageB64;

  const msgText = message || "What is this image?";
  addMessage(msgText, "user", imageToSend);
  chatHistory.push({ role: "user", content: msgText });

  textarea.value = "";
  autoResize();
  clearImage();

  // Send msgText (not bare message) so the LLM always receives a non-empty question.
  await sendMessage(msgText, imageToSend);
});
