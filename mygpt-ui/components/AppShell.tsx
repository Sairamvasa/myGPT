"use client";

import { useMemo, useState } from "react";
import ChatHeader from "./ChatHeader";
import ChatWindow from "./ChatWindow";
import Sidebar from "./Sidebar";
import ProjectsSidebar from "./ProjectsSidebar";
import ProjectWorkspace from "./ProjectWorkspace";
import type { Project } from "@/lib/api";

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
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (project: Project | null) => void;
  selectedProjectConversationId: number | null;
  onSelectProjectConversation: (conversationId: number | null) => void;
  onProjectCreated?: (project: Project) => void;
  onProjectDeleted?: (projectId: number) => void;
  onProjectUpdated?: (project: Project) => void;
};

export default function AppShell({
  conversations,
  activeChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  onChatCreated,
  onLogout,
  projects,
  selectedProject,
  onSelectProject,
  selectedProjectConversationId,
  onSelectProjectConversation,
  onProjectCreated,
  onProjectDeleted,
  onProjectUpdated,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [projectsSidebarOpen, setProjectsSidebarOpen] = useState(false);

  const currentTitle = useMemo(() => {
    if (activeChatId === null) return "New conversation";
    return (
      conversations.find((conversation) => conversation.chat_id === activeChatId)?.title ||
      "Conversation"
    );
  }, [activeChatId, conversations]);

  const isInProjectMode = selectedProject !== null;

  const displayTitle = isInProjectMode
    ? (selectedProject?.title ?? "Project")
    : currentTitle;

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

      <ProjectsSidebar
        isOpen={projectsSidebarOpen}
        onClose={() => setProjectsSidebarOpen(false)}
        selectedProjectId={selectedProject?.id ?? null}
        onSelectProject={(project) => {
          onSelectProject(project);
          setProjectsSidebarOpen(false);
        }}
        onProjectCreated={onProjectCreated}
        onProjectDeleted={onProjectDeleted}
        onLogout={onLogout}
      />

      <main className={`app-main ${isInProjectMode ? "project-mode" : ""}`}>
        <ChatHeader
          title={displayTitle}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenProjects={() => setProjectsSidebarOpen(true)}
          isInProjectMode={isInProjectMode}
          onExitProject={() => onSelectProject(null)}
          onLogout={onLogout}
        />

        {isInProjectMode ? (
          <ProjectWorkspace
            selectedProject={selectedProject}
            selectedConversationId={selectedProjectConversationId}
            onSelectConversation={onSelectProjectConversation}
            onProjectUpdated={onProjectUpdated}
            onProjectDeleted={onProjectDeleted}
          />
        ) : (
          <ChatWindow
            chatId={activeChatId}
            onChatCreated={(newId) => {
              onChatCreated(newId);
            }}
          />
        )}
      </main>
    </div>
  );
}
