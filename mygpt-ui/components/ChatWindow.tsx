"use client";

import { useEffect, useRef, useState } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import ConversationEmptyState from "./ConversationEmptyState";
import { getHistory } from "@/lib/api";

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
};

type Props = {
  chatId: number | null;
  onChatCreated?: (newChatId: number) => void;
};

export default function ChatWindow({ chatId, onChatCreated }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const previousChatIdRef = useRef<number | null>(chatId);
  const localMutationVersionRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const previousChatId = previousChatIdRef.current;
    previousChatIdRef.current = chatId;
    if (previousChatId !== null && previousChatId !== chatId) {
      localMutationVersionRef.current += 1;
    }
    const historyVersion = localMutationVersionRef.current;

    async function loadHistory() {
      if (chatId === null) {
        setMessages([]);
        return;
      }

      // A null -> id transition is the first-message path. The optimistic
      // user/assistant messages must remain visible while history catches up.
      // Clear only when the user explicitly switches between existing chats.
      if (previousChatId !== null && previousChatId !== chatId) {
        setMessages([]);
      }

      try {
        const history = await getHistory(chatId);
        if (!cancelled && historyVersion === localMutationVersionRef.current) {
          const normalizedHistory = (history || []).map(
            (message: Omit<ChatMessage, "id">, index: number) => ({
              ...message,
              id: `history-${chatId}-${index}`,
            })
          );
          setMessages((currentMessages) => {
            if (currentMessages.length === 0) {
              return normalizedHistory;
            }

            const historyCounts = new Map<string, number>();
            for (const message of normalizedHistory) {
              const key = `${message.role}\u0000${message.content}`;
              historyCounts.set(key, (historyCounts.get(key) ?? 0) + 1);
            }

            const localOnlyMessages: ChatMessage[] = [];
            for (const message of currentMessages) {
              const key = `${message.role}\u0000${message.content}`;
              const count = historyCounts.get(key) ?? 0;
              if (count > 0) {
                historyCounts.set(key, count - 1);
              } else {
                localOnlyMessages.push(message);
              }
            }

            // History may have completed before the stream persistence, so
            // retain optimistic/streamed messages not present in that result.
            return [...normalizedHistory, ...localOnlyMessages];
          });
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

  const updateMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>> = (
    update
  ) => {
    localMutationVersionRef.current += 1;
    setMessages(update);
  };

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
        setMessages={updateMessages}
        chatId={chatId}
        onChatCreated={onChatCreated}
      />
    </div>
  );
}
