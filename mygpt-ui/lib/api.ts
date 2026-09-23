// Backend API base URL.
// Uses NEXT_PUBLIC_API_URL in production (Vercel); falls back to the local
// backend for development.
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

function getApiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const body = payload as Record<string, unknown>;
  const detail = body.detail;

  if (detail && typeof detail === "object") {
    const detailBody = detail as Record<string, unknown>;
    if (typeof detailBody.message === "string") {
      return detailBody.message;
    }
  }

  if (typeof detail === "string") {
    return detail;
  }

  return typeof body.message === "string" ? body.message : fallback;
}


  // ==============================
// AUTH
// ==============================

export async function registerUser(
  name: string,
  email: string,
  password: string
) {
  const response = await fetch(`${API_URL}/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      email,
      password,
    }),
  });

  const data = await response.json();

  if (!response.ok || data.success === false) {
    throw new Error(data.message || data.detail || "Registration failed");
  }

  // Save JWT token and user info (same as login)
  if (data.access_token) {
    localStorage.setItem("access_token", data.access_token);
  }

  if (data.user_id) {
    localStorage.setItem(
      "user",
      JSON.stringify({
        user_id: data.user_id,
        name: data.name,
        email: data.email,
      })
    );
  }

  return data;
}


export async function loginUser(
  email: string,
  password: string
) {
  const response = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
    }),
  });

  const data = await response.json();

  if (!response.ok || data.success === false) {
    throw new Error(data.message || data.detail || "Login failed");
  }

  // Save JWT token
  localStorage.setItem("access_token", data.access_token);

  // Save user information
  localStorage.setItem(
    "user",
    JSON.stringify({
      user_id: data.user_id,
      name: data.name,
      email: data.email,
    })
  );

  return data;
}


export function logoutUser() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("user");
}


export function getToken() {
  if (typeof window === "undefined") {
    return null;
  }

  return localStorage.getItem("access_token");
}

function authHeaders() {
  const token = getToken();

  return {
    "Content-Type": "application/json",
    ...(token
      ? {
          Authorization: `Bearer ${token}`,
        }
      : {}),
  };
}

function bearerHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
// ==============================
// ASK AI
// ==============================

export async function askAI(
  message: string,
  chat_id: number | null
) {
  if (chat_id === null) {
    throw new Error("Create a chat before sending a message.");
  }

  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      message,
      chat_id,
    }),
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(getApiErrorMessage(detail, "Failed to get AI response"));
  }

  const data = await response.json();

  return data.answer;
}


// ==============================
// GET CHAT HISTORY
// ==============================

export async function getHistory(chatId: number) {
  const response = await fetch(
    `${API_URL}/history/${chatId}`,
    {
      headers: authHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error("Failed to load history");
  }

  return response.json();
}


// ==============================
// GET CONVERSATIONS
// ==============================

export async function getConversations() {
  const response = await fetch(`${API_URL}/conversations`, {
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw new Error("Failed to load conversations");
  }

  return response.json();
}


// ==============================
// CREATE NEW CHAT
// ==============================

export async function createNewChat() {
  const response = await fetch(`${API_URL}/new-chat`, {
    method: "POST",
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw new Error("Failed to create chat");
  }

  return response.json();
}


// ==============================
// MULTIPLE PDF UPLOAD
// ==============================

export async function uploadFiles(
  files: File[]
) {
  const formData = new FormData();

  files.forEach((file) => {
    formData.append(
      "files",
      file,
      file.name
    );
  });

  console.log(
    "Uploading PDFs:",
    files.map(
      (file) => file.name
    )
  );

  const response = await fetch(
    `${API_URL}/upload-files`,
    {
      method: "POST",
      body: formData,
      headers: bearerHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error(
      "Multiple PDF upload failed"
    );
  }

  return response.json();
}


// ==============================
// IMAGE / CAMERA ANALYSIS
// ==============================

// ==============================
// IMAGE ANALYSIS
// ==============================

export async function analyzeImage(
  file: File,
  prompt: string
) {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("prompt", prompt);

  const response = await fetch(
    `${API_URL}/vision`,
    {
      method: "POST",
      body: formData,
      headers: bearerHeaders(),
    }
  );

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(getApiErrorMessage(detail, "Image analysis failed"));
  }

  return await response.json();
}

// ==============================
// DELETE CONVERSATION
// ==============================

export async function deleteConversation(
  chatId: number
) {
  const response = await fetch(
    `${API_URL}/conversations/${chatId}`,
    {
      method: "DELETE",
      headers: authHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error("Failed to delete conversation");
  }

  return response.json();
}

export async function streamAI(
    message: string,
    chatId: number | null,
    signal?: AbortSignal
) {
    if (chatId === null) {
        throw new Error("Create a chat before sending a message.");
    }

    const response = await fetch(
        `${API_URL}/stream`,
        {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                message,
                chat_id: chatId,
            }),
            signal,
        }
    );

    if (!response.ok) {
        const errorText = await response.text().catch(() => `HTTP ${response.status}`);
        throw new Error(`Stream request failed (${response.status}): ${errorText}`);
    }

    return response.body;
}

// ==============================
// VOICE
// ==============================

export type VoiceResponse = {
  user_text: string;
  response: string;
  language: string;
  language_name: string;
  chat_id: number | null;
  audio_base64?: string | null;
  audio_format?: string | null;
  message?: string;
};

export async function sendVoiceMessage(
  audioBlob: Blob,
  chatId: number | null,
  language = "auto",
  speak = true
): Promise<VoiceResponse> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "voice-message.webm");
  formData.append("language", language);
  formData.append("speak", String(speak));
  if (chatId !== null) {
    formData.append("chat_id", String(chatId));
  }

  const token = getToken();
  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}/voice/voice`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(getApiErrorMessage(detail, "Voice request failed"));
  }

  return (await response.json()) as VoiceResponse;
}

export async function sendVoiceText(
  text: string,
  chatId: number | null,
  language = "auto",
  speak = true
): Promise<VoiceResponse> {
  const formData = new FormData();
  formData.append("text", text);
  formData.append("language", language);
  formData.append("speak", String(speak));
  if (chatId !== null) {
    formData.append("chat_id", String(chatId));
  }

  const token = getToken();
  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}/voice/chat`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(getApiErrorMessage(detail, "Voice chat failed"));
  }

  return (await response.json()) as VoiceResponse;
}
