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

function clearStoredAuthentication(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
  }
}

async function parseApiResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
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

  const data = (await parseApiResponse(response)) as Record<string, unknown>;

  if (!response.ok || data.success === false) {
    throw new Error(getApiErrorMessage(data, "Registration failed"));
  }

  // Save JWT token and user info (same as login)
  if (typeof data.access_token === "string" && data.access_token.trim()) {
    localStorage.setItem("access_token", data.access_token);
  } else {
    throw new Error("Registration response did not include an access token.");
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

  const data = (await parseApiResponse(response)) as Record<string, unknown>;

  if (!response.ok || data.success === false) {
    throw new Error(getApiErrorMessage(data, "Login failed"));
  }

  // Save JWT token
  if (typeof data.access_token !== "string" || !data.access_token.trim()) {
    throw new Error("Login response did not include an access token.");
  }
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

async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(init.headers || {}),
    },
  });

  if (response.status === 401) {
    clearStoredAuthentication();
  }
  return response;
}

function bearerHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function requestDiagnosticHeaders(): HeadersInit {
  return {
    "X-Request-ID": crypto.randomUUID(),
  };
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
    headers: { ...authHeaders(), ...requestDiagnosticHeaders() },
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
  const response = await authenticatedFetch(`${API_URL}/conversations`);

  if (!response.ok) {
    throw new Error("Failed to load conversations");
  }

  return response.json();
}


// ==============================
// CREATE NEW CHAT
// ==============================

export async function createNewChat() {
  const response = await authenticatedFetch(`${API_URL}/new-chat`, {
    method: "POST",
    headers: requestDiagnosticHeaders(),
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
    let rawText = "";
    try {
      rawText = await response.text();
      detail = JSON.parse(rawText);
    } catch {
      detail = rawText; // fallback to raw text if not JSON
    }
    throw new Error(`Image analysis failed (${response.status}): ${JSON.stringify(detail)}`);
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

    console.info("REQUEST_SENT", {
      endpoint: "/stream",
      status: response.status,
    });

    if (!response.ok) {
        if (response.status === 401) {
          clearStoredAuthentication();
        }
        const errorText = await response.text().catch(() => `HTTP ${response.status}`);
        throw new Error(`Stream request failed (${response.status}): ${errorText}`);
    }

    if (!response.body) {
        throw new Error("The stream response did not include a readable body.");
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

// ==============================
// PROJECTS
// ==============================

export interface Project {
  id: number;
  title: string;
  description: string;
  user_id: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectConversation {
  chat_id: number;
  title: string;
}

export interface ProjectFileRecord {
  id: number;
  project_id: number;
  user_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  created_at?: string | null;
}

export interface ProjectUploadResult {
  file_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  chunks: number;
}

export interface ProjectConversationResult {
  chat_id: number;
  project_id: number;
  title: string;
  project_title?: string | null;
}

export async function createProject(
  title: string,
  description: string = ""
): Promise<{ project_id: number; title: string; description: string; user_id: number }> {
  const response = await authenticatedFetch(`${API_URL}/projects`, {
    method: "POST",
    body: JSON.stringify({ title, description }),
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to create project"));
  }

  return response.json();
}

export async function getProjects(): Promise<Project[]> {
  const response = await authenticatedFetch(`${API_URL}/projects`);

  if (!response.ok) {
    throw new Error("Failed to load projects");
  }

  return response.json();
}

export async function getProject(projectId: number): Promise<Project> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}`);

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to load project"));
  }

  return response.json();
}

export async function updateProject(
  projectId: number,
  title: string,
  description: string = ""
): Promise<{ message: string }> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify({ title, description }),
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to update project"));
  }

  return response.json();
}

export async function deleteProject(projectId: number): Promise<{ message: string }> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to delete project"));
  }

  return response.json();
}

export async function createProjectConversation(
  projectId: number,
  title: string
): Promise<ProjectConversationResult> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}/conversations`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to create project conversation"));
  }

  return response.json();
}

export async function getProjectConversations(projectId: number): Promise<ProjectConversation[]> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}/conversations`);

  if (!response.ok) {
    throw new Error("Failed to load project conversations");
  }

  return response.json();
}

export async function uploadProjectFile(
  projectId: number,
  file: File,
  onProgress?: (percent: number) => void
): Promise<ProjectUploadResult> {
  const formData = new FormData();
  formData.append("file", file, file.name);

  const token = getToken();
  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}/projects/${projectId}/upload`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "File upload failed"));
  }

  return response.json();
}

export async function getProjectFiles(projectId: number): Promise<ProjectFileRecord[]> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}/files`);

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to load project files"));
  }

  return response.json();
}

export async function downloadProjectFile(
  projectId: number,
  fileId: number
): Promise<Blob> {
  const token = getToken();
  const headers: HeadersInit = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}/projects/${projectId}/files/${fileId}`, {
    headers,
  });

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to download file"));
  }

  return response.blob();
}

export async function deleteProjectFile(
  projectId: number,
  fileId: number
): Promise<{ message: string }> {
  const response = await authenticatedFetch(
    `${API_URL}/projects/${projectId}/files/${fileId}`,
    { method: "DELETE" }
  );

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to delete file"));
  }

  return response.json();
}

export interface ProjectContext {
  project: Project;
  files: Array<{
    id: number;
    filename: string;
    file_type: string;
    file_size: number;
    created_at?: string | null;
  }>;
  conversations: ProjectConversation[];
}

export async function getProjectContext(projectId: number): Promise<ProjectContext> {
  const response = await authenticatedFetch(`${API_URL}/projects/${projectId}/context`);

  if (!response.ok) {
    let detail: unknown = {};
    try {
      detail = await response.json();
    } catch {
      // ignore
    }
    throw new Error(getApiErrorMessage(detail, "Failed to load project context"));
  }

  return response.json();
}
