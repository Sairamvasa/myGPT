"use client";

import { useEffect, useState } from "react";

import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";

import {
  createNewChat,
  getConversations,
  deleteConversation,
} from "@/lib/api";

type Conversation = {
  chat_id: number;
  title: string;
};

export default function Home() {
  const [chatId, setChatId] = useState<number | null>(null);

  const [conversations, setConversations] =
    useState<Conversation[]>([]);

  async function loadConversations() {
    try {
      const data = await getConversations();

      setConversations(data);

      if (chatId === null && data.length > 0) {
        setChatId(data[0].chat_id);
      }
    } catch (error) {
      console.error(
        "Failed to load conversations:",
        error
      );
    }
  }

  useEffect(() => {
    loadConversations();
  }, []);

  async function handleNewChat() {
    try {
      const newChat = await createNewChat();

      setChatId(newChat.chat_id);

      await loadConversations();
    } catch (error) {
      console.error(
        "Failed to create new chat:",
        error
      );
    }
  }

  function handleSelectChat(id: number) {
    setChatId(id);
  }

  async function handleDeleteChat(id: number) {
    try {
      await deleteConversation(id);

      const remainingChats = conversations.filter(
        (chat) => chat.chat_id !== id
      );

      setConversations(remainingChats);

      if (chatId === id) {
        if (remainingChats.length > 0) {
          setChatId(remainingChats[0].chat_id);
        } else {
          setChatId(null);
        }
      }
    } catch (error) {
      console.error(
        "Failed to delete conversation:",
        error
      );

      alert("Unable to delete chat.");
    }
  }

  return (
    <div className="flex h-screen">
      <Sidebar
        conversations={conversations}
        activeChatId={chatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
      />

      <ChatWindow chatId={chatId} />
    </div>
  );
}