"use client";

import { useState } from "react";
import { MessageSquarePlus, MoreHorizontal, Sparkles, X } from "lucide-react";
import ConfirmDialog from "./ConfirmDialog";
import ProfileMenu from "./ProfileMenu";

type Conversation = {
  chat_id: number;
  title: string;
};

type SidebarProps = {
  conversations: Conversation[];
  activeChatId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSelectChat: (chatId: number) => void;
  onDeleteChat: (chatId: number) => void;
  onLogout: () => void;
};

export default function Sidebar({
  conversations,
  activeChatId,
  isOpen,
  onClose,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onLogout,
}: SidebarProps) {
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);

  function handleSelectChat(chatId: number) {
    onSelectChat(chatId);
    onClose();
  }

  function handleNewChat() {
    onNewChat();
    onClose();
  }

  return (
    <>
      <div
        className={`sidebar-backdrop ${isOpen ? "sidebar-backdrop-open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className={`sidebar-panel ${isOpen ? "sidebar-panel-open" : ""}`}>
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <div className="brand-mark" aria-hidden="true">
              <Sparkles size={18} />
            </div>
            <div className="brand-copy">
              <strong>MyGPT</strong>
              <span>Personal AI workspace</span>
            </div>
            <button
              type="button"
              className="icon-button icon-button-subtle sidebar-close-button"
              onClick={onClose}
              aria-label="Close sidebar"
              title="Close sidebar"
            >
              <X size={18} />
            </button>
          </div>

          <button type="button" className="sidebar-new-chat" onClick={handleNewChat}>
            <MessageSquarePlus size={18} />
            <span>New chat</span>
          </button>
        </div>

        <div className="sidebar-section-label">
          <span>Recent conversations</span>
          <span className="sidebar-count">{conversations.length}</span>
        </div>

        <nav className="conversation-list" aria-label="Recent conversations">
          {conversations.length === 0 ? (
              <div className="sidebar-empty-state">
              <MessageSquarePlus size={18} aria-hidden="true" />
              <span>Your conversations will appear here.</span>
            </div>
          ) : (
            conversations.map((conversation) => {
              const isActive = activeChatId === conversation.chat_id;

              return (
                <div
                  className={`conversation-item ${isActive ? "conversation-item-active" : ""}`}
                  key={conversation.chat_id}
                >
                  <button
                    type="button"
                    className="conversation-select"
                    onClick={() => handleSelectChat(conversation.chat_id)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <MessageSquarePlus size={16} aria-hidden="true" />
                    <span>{conversation.title || "Untitled conversation"}</span>
                  </button>
                  <button
                    type="button"
                    className="conversation-action"
                    onClick={(event) => {
                      event.stopPropagation();
                      setPendingDelete(conversation);
                    }}
                    aria-label={`Delete ${conversation.title || "conversation"}`}
                    title="Delete conversation"
                  >
                    <MoreHorizontal size={17} aria-hidden="true" />
                  </button>
                </div>
              );
            })
          )}
        </nav>

        <div className="sidebar-bottom">
          <ProfileMenu onLogout={onLogout} variant="sidebar" />
        </div>
      </aside>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        description={`This will permanently remove ${pendingDelete?.title || "this conversation"}.`}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) onDeleteChat(pendingDelete.chat_id);
          setPendingDelete(null);
        }}
      />
    </>
  );
}
