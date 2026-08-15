"use client";

import { useEffect, useState } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import { getHistory } from "@/lib/api";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type Props = {
  chatId: number | null;
  onChatCreated?: (newChatId: number) => void;
};

export default function ChatWindow({ chatId, onChatCreated }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    async function loadHistory() {
      if (chatId === null) {
        setMessages([]);
        return;
      }

      try {
        const history = await getHistory(chatId);
        setMessages(history || []);
      } catch (error) {
        console.error("Failed to load history:", error);
      }
    }

    loadHistory();
  }, [chatId]);

  return (
    <div className="flex flex-col flex-1 bg-[#202123] text-white h-full relative overflow-hidden">
      {messages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6 pt-16 md:pt-6 text-center overflow-y-auto">
          <div className="text-5xl mb-4">🤖</div>
          <h2 className="text-2xl font-bold mb-2">What would you like to explore today?</h2>
          <p className="text-gray-400 max-w-md mb-8 text-sm">
            Ask questions, run Python calculations, search the web, analyze documents, or brainstorm ideas.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full">
            <button
              onClick={() => {
                const ev = new CustomEvent("mygpt-quick-prompt", {
                  detail: "What is the latest AI and tech news today?",
                });
                window.dispatchEvent(ev);
              }}
              className="p-3 bg-[#343541] hover:bg-[#444654] rounded-xl text-left text-sm border border-zinc-700/50 transition-colors"
            >
              <span className="font-semibold block text-white">🌐 Live Web Search</span>
              <span className="text-gray-400 text-xs">"What is the latest AI news today?"</span>
            </button>

            <button
              onClick={() => {
                const ev = new CustomEvent("mygpt-quick-prompt", {
                  detail: "Calculate 2**32 / 1024 and show the math in Python",
                });
                window.dispatchEvent(ev);
              }}
              className="p-3 bg-[#343541] hover:bg-[#444654] rounded-xl text-left text-sm border border-zinc-700/50 transition-colors"
            >
              <span className="font-semibold block text-white">🐍 Python Math & Code</span>
              <span className="text-gray-400 text-xs">"Calculate 2^32 / 1024 in Python"</span>
            </button>

            <button
              onClick={() => {
                const ev = new CustomEvent("mygpt-quick-prompt", {
                  detail: "I am a Full-Stack developer. Remember my stack preferences.",
                });
                window.dispatchEvent(ev);
              }}
              className="p-3 bg-[#343541] hover:bg-[#444654] rounded-xl text-left text-sm border border-zinc-700/50 transition-colors"
            >
              <span className="font-semibold block text-white">🧠 Long-Term Memory</span>
              <span className="text-gray-400 text-xs">"Remember my stack preferences"</span>
            </button>

            <button
              onClick={() => {
                const ev = new CustomEvent("mygpt-quick-prompt", {
                  detail: "Explain quantum computing in simple terms with an analogy",
                });
                window.dispatchEvent(ev);
              }}
              className="p-3 bg-[#343541] hover:bg-[#444654] rounded-xl text-left text-sm border border-zinc-700/50 transition-colors"
            >
              <span className="font-semibold block text-white">💡 Concept Explanation</span>
              <span className="text-gray-400 text-xs">"Explain quantum computing simply"</span>
            </button>
          </div>
        </div>
      ) : (
        <MessageList messages={messages} />
      )}

      <ChatInput
        messages={messages}
        setMessages={setMessages}
        chatId={chatId}
        onChatCreated={onChatCreated}
      />
    </div>
  );
}