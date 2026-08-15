"use client";

import { useState } from "react";

type Conversation = {
  chat_id: number;
  title: string;
};

type SidebarProps = {
  conversations: Conversation[];
  activeChatId: number | null;
  onNewChat: () => void;
  onSelectChat: (chatId: number) => void;
  onDeleteChat: (chatId: number) => void;
};

export default function Sidebar({
  conversations,
  activeChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
}: SidebarProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleSelectChat = (chatId: number) => {
    onSelectChat(chatId);
    setIsOpen(false); // close sidebar on mobile after selecting
  };

  const handleNewChat = () => {
    onNewChat();
    setIsOpen(false);
  };

  return (
    <>
      {/* ── Hamburger toggle (mobile only) ── */}
      <button
        onClick={() => setIsOpen(true)}
        className="md:hidden fixed top-3 left-3 z-50 bg-zinc-800 text-white p-2 rounded-lg shadow-lg"
        aria-label="Open sidebar"
      >
        ☰
      </button>

      {/* ── Overlay backdrop (mobile only) ── */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* ── Sidebar panel ── */}
      <div
        className={`
          fixed md:relative
          top-0 left-0
          h-screen
          w-72
          bg-black text-white
          p-5
          flex flex-col
          z-50
          transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          md:translate-x-0
        `}
      >
        {/* Close button (mobile only) */}
        <button
          onClick={() => setIsOpen(false)}
          className="md:hidden self-end mb-2 text-gray-400 hover:text-white text-xl"
          aria-label="Close sidebar"
        >
          ✕
        </button>

        <h1 className="text-3xl font-bold">🤖 MyGPT</h1>

        <button
          onClick={handleNewChat}
          className="mt-6 bg-zinc-800 w-full rounded-xl p-3 hover:bg-zinc-700"
        >
          + New Chat
        </button>

        <div className="mt-6 flex-1 overflow-y-auto">
          <p className="text-sm text-gray-400 mb-3">Recent Chats</p>

          {conversations.map((chat) => (
            <div
              key={chat.chat_id}
              className={`flex items-center rounded-lg mb-1 ${
                activeChatId === chat.chat_id
                  ? "bg-zinc-700"
                  : "hover:bg-zinc-800"
              }`}
            >
              {/* Chat title */}
              <button
                onClick={() => handleSelectChat(chat.chat_id)}
                className="flex-1 text-left p-3 truncate"
              >
                {chat.title}
              </button>

              {/* Delete */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  const confirmed = window.confirm(
                    `Delete "${chat.title}"?`
                  );
                  if (confirmed) {
                    onDeleteChat(chat.chat_id);
                  }
                }}
                className="px-3 py-3 text-gray-400 hover:text-red-500"
                title="Delete chat"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}