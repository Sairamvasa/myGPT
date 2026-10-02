"use client";

import { Menu, Projector, Sparkles } from "lucide-react";
import ProfileMenu from "./ProfileMenu";

type ChatHeaderProps = {
  title: string;
  onOpenSidebar: () => void;
  onOpenProjects?: () => void;
  onExitProject?: () => void;
  isInProjectMode?: boolean;
  onLogout: () => void;
};

export default function ChatHeader({
  title,
  onOpenSidebar,
  onOpenProjects,
  onExitProject,
  isInProjectMode = false,
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

        {onOpenProjects && (
          <button
            type="button"
            className={`icon-button chat-header-menu ${isInProjectMode ? "chat-header-active" : ""}`}
            onClick={onOpenProjects}
            aria-label="Open projects"
            title="Open projects"
          >
            <Projector size={20} />
          </button>
        )}

        {isInProjectMode && onExitProject && (
          <button
            type="button"
            className="icon-button chat-header-menu chat-header-exit-project"
            onClick={onExitProject}
            aria-label="Exit project mode"
            title="Back to normal chat"
          >
            ×
          </button>
        )}

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
