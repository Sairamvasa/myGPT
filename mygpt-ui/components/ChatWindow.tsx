"use client";

import { useEffect, useState } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import ConversationEmptyState from "./ConversationEmptyState";
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
    let cancelled = false;

    async function loadHistory() {
      if (chatId === null) {
        setMessages([]);
        return;
      }

      try {
        const history = await getHistory(chatId);
        if (!cancelled) {
          setMessages(history || []);
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Failed to load history:", error);
        }
      }
    }

    void loadHistory();

    return () => {
      cancelled = true;
    };
  }, [chatId]);

  return (
    <div className="chat-window">
      <div className="chat-scroll-area">
        {messages.length === 0 ? (
          <ConversationEmptyState />
        ) : (
          <div className="conversation-container">
            <MessageList messages={messages} />
          </div>
        )}
      </div>

      <ChatInput
        setMessages={setMessages}
        chatId={chatId}
        onChatCreated={onChatCreated}
      />
    </div>
  );
}
