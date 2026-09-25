"use client";

import { useState, useEffect, useRef } from "react";
import {
  Camera,
  FilePlus2,
  FileText,
  Image,
  Mic,
  Send,
  Volume2,
  X,
  Code,
} from "lucide-react";
import {
    uploadFiles,
    analyzeImage,
    getHistory,
    streamAI,
    createNewChat,
    sendVoiceMessage,
    VoiceResponse,
} from "@/lib/api";

type ChatMessage = {
    id?: string;
    role: "user" | "assistant";
    content: string;
    regenerate?: boolean;
};

type Props = {
  setMessages: React.Dispatch<
    React.SetStateAction<ChatMessage[]>
  >;
  chatId: number | null;
  onChatCreated?: (newChatId: number) => void;
};

export default function ChatInput({
  setMessages,
  chatId,
  onChatCreated,
}: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Multiple files
  const [selectedFiles, setSelectedFiles] =
    useState<File[]>([]);

  // Voice state
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingVoice, setIsProcessingVoice] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voicePermissionError, setVoicePermissionError] = useState<string | null>(null);
  const [voiceUnsupportedError, setVoiceUnsupportedError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speakingChatIdRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const submissionInFlightRef = useRef(false);
  const activeRequestIdRef = useRef<string | null>(null);
  const activeAssistantMessageIdRef = useRef<string | null>(null);

  useEffect(() => {
    const handleQuickPrompt = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail) {
        setInput(detail);
      }
    };
    window.addEventListener("mygpt-quick-prompt", handleQuickPrompt);
    return () => window.removeEventListener("mygpt-quick-prompt", handleQuickPrompt);
  }, []);

  // Cleanup recording/audio on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = "";
      }
    };
  }, []);

  // --------------------------------
  // SEND MESSAGE
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
  // VOICE: AUDIO PLAYBACK
  // --------------------------------

  const stopAudioPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setIsSpeaking(false);
    speakingChatIdRef.current = null;
  };

  const playAudioBase64 = (base64: string, currentChatId: number | null) => {
    if (!base64) return;

    stopAudioPlayback();

    const audio = new Audio(`data:audio/mpeg;base64,${base64}`);
    audioRef.current = audio;
    speakingChatIdRef.current = currentChatId;
    setIsSpeaking(true);

    audio.play().catch((err) => {
      console.error("Audio playback failed:", err);
      stopAudioPlayback();
    });

    audio.onended = () => {
      stopAudioPlayback();
    };

    audio.onerror = () => {
      console.error("Audio playback error");
      stopAudioPlayback();
    };
  };

  // --------------------------------
  // VOICE: RECORDING
  // --------------------------------

  const startRecording = async () => {
    setVoiceError(null);
    setVoicePermissionError(null);
    setVoiceUnsupportedError(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const msg = "Your browser does not support microphone recording.";
      setVoiceUnsupportedError(msg);
      alert(msg);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // Prefer webm; fall back to browser default
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";

      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType || "audio/webm" });

        if (audioBlob.size < 4000) {
          setVoiceError("Audio too short. Please speak for at least half a second.");
          setIsRecording(false);
          return;
        }

        await processVoiceAudio(audioBlob);
      };

      mediaRecorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop());
        setIsRecording(false);
        setVoiceError("Recording failed. Please try again.");
      };

      mediaRecorder.start(250);
      setIsRecording(true);
    } catch (err: unknown) {
      console.error("Microphone error:", err);

      if (err instanceof Error) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          const msg = "Microphone access was denied. Please allow microphone access in your browser settings and try again.";
          setVoicePermissionError(msg);
          alert(msg);
        } else if (err.name === "NotFoundError") {
          const msg = "No microphone found. Please connect a microphone and try again.";
          setVoiceError(msg);
          alert(msg);
        } else {
          const msg = "Could not access microphone. Please check your device and try again.";
          setVoiceError(msg);
          alert(msg);
        }
      } else {
        const msg = "Could not access microphone. Please check your device and try again.";
        setVoiceError(msg);
        alert(msg);
      }

      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    } else {
      setIsRecording(false);
    }
  };

  const processVoiceAudio = async (audioBlob: Blob) => {
    setIsProcessingVoice(true);
    setIsRecording(false);
    try {
      let targetChatId = chatId;
      if (targetChatId === null) {
        try {
          const newChat = await createNewChat();
          targetChatId = newChat.chat_id;
          onChatCreated?.(newChat.chat_id);
        } catch (err) {
          console.warn("Could not create chat session on server", err);
          throw new Error("Unable to create a chat. Please try again.");
        }
      }

      const result: VoiceResponse = await sendVoiceMessage(audioBlob, targetChatId, "auto", true);

      const userText = (result.user_text || "").trim();
      const assistantText = (result.response || "").trim();

      if (userText) {
        setMessages((previous) => [
          ...previous,
          { role: "user", content: userText },
        ]);
      }

      if (assistantText) {
        setMessages((previous) => [
          ...previous,
          { role: "assistant", content: assistantText },
        ]);
      }

      if (result.audio_base64 && result.audio_format === "mp3") {
        playAudioBase64(result.audio_base64, result.chat_id ?? targetChatId);
      }
    } catch (err: unknown) {
      console.error("Voice processing failed:", err);
      const message = err instanceof Error ? err.message : "Voice processing failed. Please try again.";
      setVoiceError(message);
    } finally {
      setIsProcessingVoice(false);
    }
  };

  // --------------------------------
  // SEND MESSAGE
  // --------------------------------

  const sendMessage = async () => {
    if (
      submissionInFlightRef.current ||
      loading ||
      isRecording ||
      isProcessingVoice ||
      isSpeaking
    ) {
      return;
    }
    submissionInFlightRef.current = true;
    const requestId = crypto.randomUUID();
    activeRequestIdRef.current = requestId;

    // Stop any ongoing voice activity
    stopAudioPlayback();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }

    const userText = input.trim();

    if (
      !userText &&
      selectedFiles.length === 0
    ) {
      submissionInFlightRef.current = false;
      activeRequestIdRef.current = null;
      return;
    }
    const submittedText = userText;

    // Copy files before clearing UI
    const filesToProcess = [
      ...selectedFiles
    ];
    const userDisplayText =
      submittedText ||
      filesToProcess.map((file) => `📄 ${file.name}`).join("\n");
    const userMessageId = crypto.randomUUID();
    console.info("SEND_START", {
      requestId,
      submittedTextLength: submittedText.length,
      chatIdBefore: chatId,
    });
    setMessages((previous) => [
      ...previous,
      { id: userMessageId, role: "user", content: userDisplayText },
    ]);

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

    let createdChatId: number | null = null;

    try {
      setLoading(true);

      // Auto-create chat if starting from a clean new session
      let targetChatId = chatId;
      if (targetChatId === null) {
        try {
          const newChat = await createNewChat();
          targetChatId = newChat.chat_id;
          createdChatId = newChat.chat_id;
        } catch (err) {
          console.warn("Could not create chat session on server", err);
          throw new Error("Unable to create a chat. Please try again.");
        }
      }
      console.info("CHAT_RESOLVED", { requestId, resolvedChatId: targetChatId });

      // Abort any stale controller and create a new one for this request
      abortControllerRef.current?.abort();
      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      const isActiveRequest = () =>
        activeRequestIdRef.current === requestId &&
        !abortController.signal.aborted;

      // =================================
      // DOCUMENTS (PDFs, TEXT, CODE)
      // =================================

      if (documentFiles.length > 0) {
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
        if (submittedText) {
          const stream = await streamAI(
            submittedText,
            targetChatId,
            abortController.signal
          );

if (!stream) {
    throw new Error("No stream received.");
}

const reader = stream.getReader();

const decoder = new TextDecoder();

let answer = "";
let assistantMessageId: string | null = null;
let firstChunkLogged = false;

while (true) {

    if (abortController.signal.aborted) {

        reader.cancel();

        break;
    }

    const { done, value } = await reader.read();

    if (done) break;

    if (!isActiveRequest()) break;
    answer += decoder.decode(value, { stream: true });
    if (!answer) continue;

    setMessages((previous) => {
        if (!assistantMessageId) {
            assistantMessageId = crypto.randomUUID();
            activeAssistantMessageIdRef.current = assistantMessageId;
            return [
              ...previous,
              { id: assistantMessageId, role: "assistant", content: answer, isStreaming: true },
            ];
        }
        return previous.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: answer, isStreaming: true }
            : message
        );
    });
    if (!firstChunkLogged) {
      firstChunkLogged = true;
      console.info("FIRST_CHUNK", { requestId, chunkLength: value?.length ?? 0 });
    }

}
const trailingText = decoder.decode();
if (trailingText) {
    answer += trailingText;
}
if (isActiveRequest()) setMessages((previous) => {
    const finalAnswer = answer.trim()
        ? answer
        : "⚠️ No answer was received. Please try again.";

    if (!assistantMessageId) {
        return [...previous, { id: crypto.randomUUID(), role: "assistant", content: finalAnswer, isStreaming: false }];
    }
    return previous.map((message) =>
      message.id === assistantMessageId
        ? { ...message, content: finalAnswer, isStreaming: false }
        : message
    );
});
console.info("REQUEST_FINISHED", { requestId, answerLength: answer.length });
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
                id: crypto.randomUUID(),
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
        id: crypto.randomUUID(),
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
        const stream = await streamAI(
          submittedText,
          targetChatId,
          abortController.signal
        );

if (!stream) {
    throw new Error("No stream received.");
}

const reader = stream.getReader();
const decoder = new TextDecoder();

let answer = "";
let assistantMessageId: string | null = null;
let firstChunkLogged = false;

while (true) {

    if (abortController.signal.aborted) {
        await reader.cancel();
        break;
    }

    const { done, value } = await reader.read();

    if (done) break;

    if (!isActiveRequest()) break;
    answer += decoder.decode(value, { stream: true });
    if (!answer) continue;

    setMessages((previous) => {
        if (!assistantMessageId) {
          assistantMessageId = crypto.randomUUID();
          activeAssistantMessageIdRef.current = assistantMessageId;
          return [
            ...previous,
            { id: assistantMessageId, role: "assistant", content: answer, isStreaming: true, regenerate: true },
          ];
        }
        return previous.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: answer, isStreaming: true }
            : message
        );
    });
    if (!firstChunkLogged) {
      firstChunkLogged = true;
      console.info("FIRST_CHUNK", { requestId, chunkLength: value?.length ?? 0 });
    }
}
const trailingText = decoder.decode();
if (trailingText) {
    answer += trailingText;
}

// Remove cursor after completion
if (isActiveRequest()) setMessages((previous) => {
    const finalAnswer = answer.trim()
      ? answer
      : "⚠️ No answer was received. Please try again.";

    if (!assistantMessageId) {
      return [...previous, { id: crypto.randomUUID(), role: "assistant", content: finalAnswer, isStreaming: false }];
    }
    return previous.map((message) =>
      message.id === assistantMessageId
        ? { ...message, content: finalAnswer, isStreaming: false }
        : message
    );
});
console.info("REQUEST_FINISHED", { requestId, answerLength: answer.length });
      }

      // Reconcile the committed exchange after streaming. This closes the
      // race where the initial history request finishes between the user
      // update and the assistant update.
      if (targetChatId !== null && isActiveRequest()) {
        try {
          const history = await getHistory(targetChatId);
          if (isActiveRequest()) {
            setMessages(
              (history || []).map(
                (message: { role: "user" | "assistant"; content: string }, index: number) => ({
                  ...message,
                  id: `history-${targetChatId}-${index}`,
                })
              )
            );
          }
        } catch (historyError) {
          console.warn("Unable to reconcile streamed chat history:", historyError);
        }
      }

    } catch (error: unknown) {
      // Handle AbortError as expected user cancellation, not an error
      if (error instanceof Error && error.name === "AbortError") {
        console.log("Generation aborted by user");
      } else {
        console.error(
          "FILE / AI ERROR:",
          error
        );

        const errorMessage =
          error instanceof Error
            ? `❌ Error: ${error.message}`
            : "❌ Unable to process the request. Please try again.";

        if (activeRequestIdRef.current === requestId) {
          setMessages(
            (previous) => {
              const updated = activeAssistantMessageIdRef.current
                ? previous.map((message) =>
                    message.id === activeAssistantMessageIdRef.current
                      ? { ...message, isStreaming: false }
                      : message
                  )
                : previous;
              return [
                ...updated,
                {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content: errorMessage,
                  isStreaming: false,
                },
              ];
            }
          );
        }
      }
    } finally {
      submissionInFlightRef.current = false;
      abortControllerRef.current = null;
      if (activeRequestIdRef.current === requestId) {
        // Keep the completed request identity until the next send. React may
        // execute queued functional state updaters after this async function
        // returns; clearing it here would discard the final assistant update.
        setLoading(false);
      }
      if (activeRequestIdRef.current === requestId) {
        activeAssistantMessageIdRef.current = null;
      }
    }
  };

  // Stop audio when switching chats
  const previousChatIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (previousChatIdRef.current !== null && previousChatIdRef.current !== chatId) {
      stopAudioPlayback();
    }
    previousChatIdRef.current = chatId;
  }, [chatId]);

  return (
    <div className="composer-dock">
      <div className="composer-shell">

      {/* SELECTED FILE PREVIEW */}

      {selectedFiles.length > 0 && (
        <div className="attachment-summary">

          <div className="attachment-count">
            <FilePlus2 size={15} aria-hidden="true" />
            {selectedFiles.length} file(s) selected
          </div>

          <div className="attachment-list">

{selectedFiles.map(
              (file, index) => (
                <div
                  key={`${file.name}-${file.size}-${index}`}
                  className="attachment-chip"
                >
                  <span className="attachment-icon" aria-hidden="true">
                    {file.type.startsWith("image/") ? (
                      // eslint-disable-next-line jsx-a11y/alt-text
                      <Image size={15} aria-hidden="true" />
                    ) : file.name.endsWith(".pdf") ? (
                      <FileText size={15} aria-hidden="true" />
                    ) : (
                      <Code size={15} aria-hidden="true" />
                    )}
                  </span>

                  <span className="attachment-name">
                    {file.name}
                  </span>

                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    className="attachment-remove"
                    title="Remove file"
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </div>
              )
            )}

          </div>
        </div>
      )}

      {/* INPUT AREA */}

      {(voiceError || voicePermissionError || voiceUnsupportedError) && (
        <div className="composer-error">
          {voicePermissionError || voiceUnsupportedError || voiceError}
          <button
            type="button"
            onClick={() => {
              setVoiceError(null);
              setVoicePermissionError(null);
              setVoiceUnsupportedError(null);
            }}
            className="composer-error-dismiss"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="composer-controls">

{/* FILE BUTTON */}

        <label
          className={`composer-icon-button ${
            loading
              ? "is-disabled"
              : ""
          }`}
          title="Attach file (PDF, image, or code file)"
          aria-label="Attach file"
          data-icon="file"
        >
          <FilePlus2 size={18} aria-hidden="true" />

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
          className={`composer-icon-button ${
            loading || isRecording || isProcessingVoice || isSpeaking
              ? "is-disabled"
              : ""
          }`}
          title="Take a photo"
          aria-label="Take a photo"
        >
          <Camera size={18} aria-hidden="true" />

          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileSelect}
            className="hidden"
            disabled={loading || isRecording || isProcessingVoice || isSpeaking}
          />
        </label>

        {/* VOICE BUTTON / STATUS */}

        {isRecording ? (
          <button
            type="button"
            onClick={stopRecording}
            className="composer-action-button composer-recording"
            title="Stop recording"
          >
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </span>
            <span className="hidden sm:inline">Recording</span>
          </button>
        ) : isProcessingVoice ? (
          <button
            type="button"
            disabled
            className="composer-action-button is-processing"
            title="Processing voice"
          >
            <span className="animate-spin inline-block h-4 w-4 border-2 border-white border-t-transparent rounded-full"></span>
            <span className="hidden sm:inline">Processing</span>
          </button>
) : isSpeaking ? (
          <button
            type="button"
            onClick={stopAudioPlayback}
            className="composer-action-button is-speaking"
            title="Stop audio"
            aria-label="Stop audio"
          >
            <Volume2 size={17} aria-hidden="true" />
            <span className="hidden sm:inline">Speaking</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={startRecording}
            disabled={loading}
            className={`composer-icon-button ${
              loading
                ? "is-disabled"
                : ""
            }`}
            title="Record voice message"
            aria-label="Record voice message"
          >
            <Mic size={18} aria-hidden="true" />
          </button>
        )}

        {/* TEXT INPUT */}

        <input
          className="composer-input"
          placeholder={
            selectedFiles.length > 0
              ? `Ask something about ${selectedFiles.length} selected file(s)...`
              : isRecording
              ? "Listening..."
              : isProcessingVoice
              ? "Processing voice..."
              : isSpeaking
              ? "Playing response..."
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
          disabled={loading || isRecording || isProcessingVoice || isSpeaking}
        />

{/* SEND BUTTON */}

        <button
    type="button"
    onClick={() => {
      if (loading) {
        activeRequestIdRef.current = null;
        const assistantMessageId = activeAssistantMessageIdRef.current;
        if (assistantMessageId) {
          setMessages((previous) =>
            previous.map((message) =>
              message.id === assistantMessageId
                ? { ...message, isStreaming: false }
                : message
            )
          );
        }
        abortControllerRef.current?.abort();
        setLoading(false);
      } else {
        void sendMessage();
      }
    }}
    disabled={
        !loading &&
        (isRecording || isProcessingVoice || isSpeaking) &&
        !input.trim() &&
        selectedFiles.length === 0
    }
    className={`composer-send-button ${
        loading
            ? "is-stop"
            : ""
    }`}
>
    <Send size={16} aria-hidden="true" />
    {loading ? "⏹ Stop" : "🚀 Send"}
</button>

      </div>
      </div>
    </div>
  );

}
