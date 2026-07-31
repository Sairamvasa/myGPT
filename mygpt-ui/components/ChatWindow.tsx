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
};

export default function ChatWindow({ chatId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    async function loadHistory() {
      if (chatId === null) {
        setMessages([]);
        return;
      }

      try {
        const history = await getHistory(chatId);

        console.log("History:", history);

        setMessages(history);
      } catch (error) {
        console.error("Failed to load history:", error);
      }
    }

    loadHistory();
  }, [chatId]);

  if (chatId === null) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#202123] text-white">
        Click New Chat to start
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 bg-[#202123] text-white">
      <MessageList messages={messages} />

      <ChatInput
        messages={messages}
        setMessages={setMessages}
        chatId={chatId}
      />
    </div>
  );
}