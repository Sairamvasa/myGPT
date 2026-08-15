// Backend API URL
// PC IPv4 address: 192.168.1.34
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://mygpt-production-97da.up.railway.app";


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
// ==============================
// ASK AI
// ==============================

export async function askAI(
  message: string,
  chat_id: number | null
) {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      message,
      chat_id: chat_id || 1,
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to get AI response");
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
      file
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
      headers: authHeaders(),
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
    }
  );

  if (!response.ok) {
    throw new Error("Image analysis failed");
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
    chatId: number | null
) {
    const response = await fetch(
        `${API_URL}/stream`,
        {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                message,
                chat_id: chatId || 1,
            }),
        }
    );

    return response.body;
}