"use client";

import { Menu, Sparkles } from "lucide-react";
import ProfileMenu from "./ProfileMenu";

type ChatHeaderProps = {
  title: string;
  onOpenSidebar: () => void;
  onLogout: () => void;
};

export default function ChatHeader({
  title,
  onOpenSidebar,
  onLogout,
}: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div className="chat-header-leading">
        <button
          type="button"
          className="icon-button chat-header-menu"
          onClick={onOpenSidebar}
          aria-label="Open conversation sidebar"
          title="Open sidebar"
        >
          <Menu size={20} />
        </button>

        <span className="chat-header-brand" aria-hidden="true">
          <Sparkles size={17} />
        </span>
        <div className="chat-header-title-group">
          <span className="chat-header-brand-name">MyGPT</span>
          <h1 className="chat-header-title">{title}</h1>
        </div>
      </div>

      <ProfileMenu onLogout={onLogout} variant="header" />
    </header>
  );
}
