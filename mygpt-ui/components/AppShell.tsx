"use client";

import { useMemo, useState } from "react";
import ChatHeader from "./ChatHeader";
import ChatWindow from "./ChatWindow";
import Sidebar from "./Sidebar";

type Conversation = {
  chat_id: number;
  title: string;
};

type AppShellProps = {
  conversations: Conversation[];
  activeChatId: number | null;
  onNewChat: () => void;
  onSelectChat: (chatId: number) => void;
  onDeleteChat: (chatId: number) => void;
  onChatCreated: (chatId: number) => void;
  onLogout: () => void;
};

export default function AppShell({
  conversations,
  activeChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onChatCreated,
  onLogout,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const currentTitle = useMemo(() => {
    if (activeChatId === null) return "New conversation";
    return (
      conversations.find((conversation) => conversation.chat_id === activeChatId)?.title ||
      "Conversation"
    );
  }, [activeChatId, conversations]);

  return (
    <div className="app-shell">
      <Sidebar
        conversations={conversations}
        activeChatId={activeChatId}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={onNewChat}
        onSelectChat={onSelectChat}
        onDeleteChat={onDeleteChat}
        onLogout={onLogout}
      />

      <main className="app-main">
        <ChatHeader
          title={currentTitle}
          onOpenSidebar={() => setSidebarOpen(true)}
          onLogout={onLogout}
        />
        <ChatWindow chatId={activeChatId} onChatCreated={onChatCreated} />
      </main>
    </div>
  );
}
