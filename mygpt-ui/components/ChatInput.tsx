"use client";

import { useState, useEffect } from "react";
import {
    askAI,
    uploadFiles,
    analyzeImage,
    streamAI,
    createNewChat,
} from "@/lib/api";

type ChatMessage = {
    role: "user" | "assistant";
    content: string;
    regenerate?: boolean;
};

type Props = {
  messages: ChatMessage[];
  setMessages: React.Dispatch<
    React.SetStateAction<ChatMessage[]>
  >;
  chatId: number | null;
  onChatCreated?: (newChatId: number) => void;
};

export default function ChatInput({
  messages,
  setMessages,
  chatId,
  onChatCreated,
}: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stopGeneration, setStopGeneration] = useState(false);
  // Multiple files
  const [selectedFiles, setSelectedFiles] =
    useState<File[]>([]);

  useEffect(() => {
    const handleQuickPrompt = (e: any) => {
      if (e.detail) {
        setInput(e.detail);
      }
    };
    window.addEventListener("mygpt-quick-prompt", handleQuickPrompt);
    return () => window.removeEventListener("mygpt-quick-prompt", handleQuickPrompt);
  }, []);

  // --------------------------------
  // SELECT FILES
  // --------------------------------

  const handleFileSelect = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const newFiles = Array.from(
      e.target.files || []
    );

    if (newFiles.length === 0) {
      return;
    }

    console.log(
      "FILES SELECTED:",
      newFiles.map((file) => file.name)
    );

    const allowedTypes = [
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
      // All text / code types — browsers may report these as text/plain
      // or a specific MIME; we also allow by extension below
      "text/plain",
      "text/html",
      "text/css",
      "text/javascript",
      "text/typescript",
      "text/x-python",
      "application/javascript",
      "application/typescript",
      "application/json",
      "text/csv",
      "text/markdown",
      "text/xml",
      "application/xml",
      "text/yaml",
      "application/x-yaml",
      "application/x-sh",
    ];

    // Also allow by file extension for types browsers label as "text/plain"
    const allowedExtensions = [
      ".pdf",
      ".jpg", ".jpeg", ".png", ".webp",
      ".py", ".js", ".ts", ".tsx", ".jsx",
      ".html", ".htm", ".css", ".scss", ".sass",
      ".json", ".jsonc", ".csv", ".tsv",
      ".md", ".markdown", ".txt",
      ".xml", ".yaml", ".yml", ".toml", ".ini",
      ".sh", ".bash", ".bat", ".ps1",
      ".c", ".cpp", ".h", ".java", ".go",
      ".rs", ".rb", ".php", ".swift", ".kt",
      ".sql", ".r", ".scala", ".lua",
    ];

    const validFiles = newFiles.filter((file) => {
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      return allowedTypes.includes(file.type) || allowedExtensions.includes(ext);
    });

    if (validFiles.length !== newFiles.length) {
      alert(
        "Some files are not supported. Supported types: PDF, images (JPG/PNG/WEBP), and code/text files (py, js, ts, html, css, json, csv, md, txt, etc.)"
      );
    }

    setSelectedFiles((previousFiles) => {
      const updatedFiles = [
        ...previousFiles
      ];

      for (const file of validFiles) {
        // Prevent exact duplicate selections
        const alreadyExists =
          updatedFiles.some(
            (existingFile) =>
              existingFile.name === file.name &&
              existingFile.size === file.size &&
              existingFile.lastModified ===
                file.lastModified
          );

        if (!alreadyExists) {
          updatedFiles.push(file);
        }
      }

      console.log(
        "TOTAL SELECTED FILES:",
        updatedFiles.map(
          (file) => file.name
        )
      );

      return updatedFiles;
    });

    // Allows selecting same input again
    e.target.value = "";
  };

  // --------------------------------
  // REMOVE ONE FILE
  // --------------------------------

  const removeFile = (index: number) => {
    if (loading) return;

    setSelectedFiles((previousFiles) =>
      previousFiles.filter(
        (_, fileIndex) =>
          fileIndex !== index
      )
    );
  };

  // --------------------------------
  // SEND MESSAGE
  // --------------------------------

  const sendMessage = async () => {
    if (loading) {
      return;
    }

    const userText = input.trim();

    if (
      !userText &&
      selectedFiles.length === 0
    ) {
      return;
    }

    // Copy files before clearing UI
    const filesToProcess = [
      ...selectedFiles
    ];

    const documentFiles =
      filesToProcess.filter(
        (file) =>
          !file.type.startsWith(
            "image/"
          )
      );

    const imageFiles =
      filesToProcess.filter(
        (file) =>
          file.type.startsWith(
            "image/"
          )
      );

    console.log(
      "ALL FILES TO PROCESS:",
      filesToProcess.map(
        (file) => file.name
      )
    );

    console.log(
      "DOCUMENT FILES TO UPLOAD:",
      documentFiles.map(
        (file) => file.name
      )
    );

    console.log(
      "IMAGE FILES:",
      imageFiles.map(
        (file) => file.name
      )
    );

    setInput("");
    setSelectedFiles([]);

    try {
      setStopGeneration(false);
      setLoading(true);

      // Auto-create chat if starting from a clean new session
      let targetChatId = chatId;
      if (!targetChatId) {
        try {
          const newChat = await createNewChat();
          targetChatId = newChat.chat_id;
          if (onChatCreated) {
            onChatCreated(newChat.chat_id);
          }
        } catch (err) {
          console.warn("Could not create chat session on server, using session fallback", err);
          targetChatId = 1;
        }
      }

      // =================================
      // DOCUMENTS (PDFs, TEXT, CODE)
      // =================================

      if (documentFiles.length > 0) {
        setMessages((previous) => [
          ...previous,
          {
            role: "user",
            content:
              documentFiles
                .map(
                  (file) =>
                    `📄 ${file.name}`
                )
                .join("\n") +
              (userText
                ? `\n\n${userText}`
                : ""),
          },
        ]);

        console.log(
          `Uploading ${documentFiles.length} document(s)...`
        );

        const uploadResult =
          await uploadFiles(
            documentFiles
          );

        console.log(
          "PDF UPLOAD RESULT:",
          uploadResult
        );

        const successfulCount =
          uploadResult?.successful ??
          documentFiles.length;

        const totalCount =
          uploadResult?.total ??
          documentFiles.length;

        // If backend reports failure
        if (successfulCount === 0) {
          throw new Error(
            "Backend could not process any document."
          );
        }

        // User uploaded PDFs and asked
        // a question at the same time
        if (userText) {
          const stream = await streamAI(
            userText,
            targetChatId
          );

if (!stream) {
    throw new Error("No stream received.");
}

const reader = stream.getReader();

const decoder = new TextDecoder();

let answer = "";

setMessages((previous) => [
    ...previous,
    {
        role: "assistant",
        content: "",
    },
]);

while (true) {

    if (stopGeneration) {

        reader.cancel();

        break;
    }

    const { done, value } = await reader.read();

    if (done) break;

    answer += decoder.decode(value);

    setMessages((previous) => {

        const updated = [...previous];

        updated[updated.length - 1] = {
            role: "assistant",
            content: answer + "▌",
        };

        return updated;
    });

}
setMessages((previous) => {

    const updated = [...previous];

    updated[updated.length - 1] = {
        role: "assistant",
        content: answer,
    };

    return updated;
});
        } else {
          let message =
            `📚 ${successfulCount} of ${totalCount} document file(s) processed successfully.`;

          if (
            successfulCount <
            totalCount
          ) {
            message +=
              "\n\n⚠️ Some documents could not be processed. Check the backend terminal for details.";
          } else {
            message +=
              "\n\nYou can now ask questions about all uploaded documents.";
          }

          setMessages(
            (previous) => [
              ...previous,
              {
                role: "assistant",
                content: message,
              },
            ]
          );
        }
      }

      // =================================
      // IMAGES
      // =================================

      if (imageFiles.length > 0) {
        const question =
          userText ||
          "Analyze this image in detail.";

        for (
          const imageFile
          of imageFiles
        ) {
          setMessages(
            (previous) => [
              ...previous,
              {
                role: "user",
                content:
                  `🖼️ ${imageFile.name}` +
                  `\n\n${question}`,
              },
            ]
          );

          console.log(
            "Analyzing image:",
            imageFile.name
          );

          const result = await analyzeImage(
    imageFile,
    question
);

console.log(result);

setMessages((previous) => [
    ...previous,
    {
        role: "assistant",
        content:
            `🖼️ ${imageFile.name}\n\n${result.answer}`,
    },
]);
        }
      }

      // =================================
      // NORMAL TEXT MESSAGE
      // =================================

      if (
        filesToProcess.length === 0 &&
        userText
      ) {
        setMessages(
          (previous) => [
            ...previous,
            {
              role: "user",
              content: userText,
            },
          ]
        );

        const stream = await streamAI(
          userText,
          targetChatId
        );

if (!stream) {
    throw new Error("No stream received.");
}

const reader = stream.getReader();
const decoder = new TextDecoder();

let answer = "";

// Empty assistant message
setMessages((previous) => [
    ...previous,
    
{
    role: "assistant",
    content: answer,
    regenerate: true,
},
]);

while (true) {

    if (stopGeneration) {
        await reader.cancel();
        break;
    }

    const { done, value } = await reader.read();

    if (done) break;

    answer += decoder.decode(value, { stream: true });

    setMessages((previous) => {

        const updated = [...previous];

        updated[updated.length - 1] = {
            role: "assistant",
            content: answer + "▌",
        };

        return updated;
    });
}

// Remove cursor after completion
setMessages((previous) => {

    const updated = [...previous];

    updated[updated.length - 1] = {
        role: "assistant",
        content: answer,
    };

    return updated;
});
      }
    } catch (error) {
      console.error(
        "FILE / AI ERROR:",
        error
      );

      setMessages(
        (previous) => [
          ...previous,
          {
            role: "assistant",
            content:
              "Unable to process the selected file(s). Please check the backend terminal.",
          },
        ]
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-3 md:p-4 border-t border-gray-700">

      {/* SELECTED FILE PREVIEW */}

      {selectedFiles.length > 0 && (
        <div className="mb-3">

          <div className="mb-2 text-sm text-gray-400">
            {selectedFiles.length} file(s) selected
          </div>

          <div className="flex flex-wrap gap-2">

            {selectedFiles.map(
              (file, index) => (
                <div
                  key={`${file.name}-${file.size}-${index}`}
                  className="inline-flex items-center gap-3 bg-gray-700 px-4 py-2 rounded-xl text-white"
                >
                  <span>
                    {file.type.startsWith("image/")
                      ? "🖼️"
                      : file.name.endsWith(".pdf")
                      ? "📄"
                      : "💻"}
                  </span>

                  <span className="max-w-[200px] truncate">
                    {file.name}
                  </span>

                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    className="text-gray-400 hover:text-red-400 ml-1 font-bold text-sm px-1"
                    title="Remove file"
                  >
                    ✕
                  </button>
                </div>
              )
            )}

          </div>
        </div>
      )}

      {/* INPUT AREA */}

      <div className="flex gap-2 flex-wrap sm:flex-nowrap">

        {/* FILE BUTTON */}

        <label
          className={`bg-gray-700 text-white px-4 py-2 rounded ${
            loading
              ? "opacity-50 cursor-not-allowed"
              : "cursor-pointer hover:bg-gray-600"
          }`}
          title="Attach file (PDF, image, or code file)"
        >
          📎

          <input
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
            disabled={loading}
          />
        </label>

        {/* CAMERA BUTTON */}

<label
  className={`bg-gray-700 text-white px-4 py-2 rounded ${
    loading
      ? "opacity-50 cursor-not-allowed"
      : "cursor-pointer hover:bg-gray-600"
  }`}
  title="Take a photo"
>
  📷

  <input
    type="file"
    accept="image/*"
    capture="environment"
    onChange={handleFileSelect}
    className="hidden"
    disabled={loading}
  />
</label>

        {/* TEXT INPUT */}

        <input
          className="flex-1 min-w-0 p-2 rounded bg-gray-800 text-white text-sm md:text-base"
          placeholder={
            selectedFiles.length > 0
              ? `Ask something about ${selectedFiles.length} selected file(s)...`
              : "Type your message..."
          }
          value={input}
          onChange={(e) =>
            setInput(
              e.target.value
            )
          }
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey
            ) {
              e.preventDefault();
              sendMessage();
            }
          }}
          disabled={loading}
        />

        {/* SEND BUTTON */}

        <button
    type="button"
    onClick={
        loading
            ? () => setStopGeneration(true)
            : sendMessage
    }
    disabled={
        !loading &&
        !input.trim() &&
        selectedFiles.length === 0
    }
    className={
        loading
            ? "bg-red-600 px-4 py-2 rounded text-white"
            : "bg-blue-600 px-4 py-2 rounded text-white"
    }
>
    {loading ? "⏹ Stop" : "🚀 Send"}
</button>

      </div>
    </div>
  );

}


