"use client";

import { useState } from "react";
import {
    askAI,
    uploadFiles,
    analyzeImage,
    streamAI,
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
  chatId: number;
};

export default function ChatInput({
  messages,
  setMessages,
  chatId,
}: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [stopGeneration, setStopGeneration] = useState(false);
  // Multiple files
  const [selectedFiles, setSelectedFiles] =
    useState<File[]>([]);
    

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
    ];

    const validFiles = newFiles.filter(
      (file) =>
        allowedTypes.includes(file.type)
    );

    if (validFiles.length !== newFiles.length) {
      alert(
        "Only PDF, JPG, JPEG, PNG and WEBP files are supported."
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

    const pdfFiles =
      filesToProcess.filter(
        (file) =>
          file.type ===
          "application/pdf"
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
      "PDF FILES TO UPLOAD:",
      pdfFiles.map(
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

      // =================================
      // MULTIPLE PDFs
      // =================================

      if (pdfFiles.length > 0) {
        setMessages((previous) => [
          ...previous,
          {
            role: "user",
            content:
              pdfFiles
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
          `Uploading ${pdfFiles.length} PDFs...`
        );

        const uploadResult =
          await uploadFiles(
            pdfFiles
          );

        console.log(
          "PDF UPLOAD RESULT:",
          uploadResult
        );

        const successfulCount =
          uploadResult?.successful ??
          pdfFiles.length;

        const totalCount =
          uploadResult?.total ??
          pdfFiles.length;

        // If backend reports failure
        if (successfulCount === 0) {
          throw new Error(
            "Backend could not process any PDF."
          );
        }

        // User uploaded PDFs and asked
        // a question at the same time
        if (userText) {
const stream = await streamAI(
    userText,
    chatId
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
            `📚 ${successfulCount} of ${totalCount} PDF file(s) processed successfully.`;

          if (
            successfulCount <
            totalCount
          ) {
            message +=
              "\n\n⚠️ Some PDFs could not be processed. Check the backend terminal for details.";
          } else {
            message +=
              "\n\nYou can now ask questions about all uploaded PDFs.";
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
    chatId
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
    <div className="p-4 border-t border-gray-700">

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
                    {file.type.startsWith(
                      "image/"
                    )
                      ? "🖼️"
                      : "📄"}
                  </span>

                  <span className="max-w-[200px] truncate">
                    {file.name}
                  </span>

{/* SEND BUTTON */}

<button
    type="button"
    onClick={sendMessage}
    disabled={
        loading ||
        (
            !input.trim() &&
            selectedFiles.length === 0
        )
    }
    className={`
        px-5
        py-2
        rounded-lg
        font-semibold
        transition-all
        duration-200

        ${
            loading
                ? "bg-gray-600 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700 active:scale-95"
        }

        text-white
    `}
>

    {loading ? (

        <span className="flex items-center gap-2">

            <span className="animate-pulse">
                🤖
            </span>

            Thinking...

        </span>

    ) : (

        <span className="flex items-center gap-2">

            <span>🚀</span>

            Send

        </span>

    )}

</button>
                </div>
              )
            )}

          </div>
        </div>
      )}

      {/* INPUT AREA */}

      <div className="flex gap-2">

        {/* FILE BUTTON */}

        <label
          className={`bg-gray-700 text-white px-4 py-2 rounded ${
            loading
              ? "opacity-50 cursor-not-allowed"
              : "cursor-pointer hover:bg-gray-600"
          }`}
        >
          📎

          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp"
            multiple
            onChange={
              handleFileSelect
            }
            className="hidden"
            disabled={
              loading
            }
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
          className="flex-1 p-2 rounded bg-gray-800 text-white"
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


