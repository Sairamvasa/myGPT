// Backend API URL
// PC IPv4 address: 192.168.1.34
const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";


// ==============================
// ASK AI
// ==============================

export async function askAI(
  message: string,
  chat_id: number
) {
  const response = await fetch(
    `${API_URL}/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        chat_id,
      }),
    }
  );

  if (!response.ok) {
    throw new Error(
      "Failed to get AI response"
    );
  }

  const data = await response.json();

  return data.answer;
}


// ==============================
// GET CHAT HISTORY
// ==============================

export async function getHistory(
  chatId: number
) {
  const response = await fetch(
    `${API_URL}/history/${chatId}`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to load history"
    );
  }

  return response.json();
}


// ==============================
// GET CONVERSATIONS
// ==============================

export async function getConversations() {
  const response = await fetch(
    `${API_URL}/conversations`
  );

  if (!response.ok) {
    throw new Error(
      "Failed to load conversations"
    );
  }

  return response.json();
}


// ==============================
// CREATE NEW CHAT
// ==============================

export async function createNewChat() {
  const response = await fetch(
    `${API_URL}/new-chat`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    throw new Error(
      "Failed to create chat"
    );
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
    }
  );

  if (!response.ok) {
    throw new Error(
      "Failed to delete conversation"
    );
  }

  return response.json();
}

export async function streamAI(
    message: string,
    chatId: number
) {
    const response = await fetch(
        `${API_URL}/stream`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                chat_id: chatId,
            }),
        }
    );

    return response.body;
}