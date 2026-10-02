"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  MessageSquarePlus,
  Plus,
  Edit3,
} from "lucide-react";
import ChatWindow from "./ChatWindow";
import {
  getProjectConversations,
  createProjectConversation,
  type Project,
  type ProjectConversation,
} from "@/lib/api";
import ProjectCreationModal from "./ProjectCreationModal";
import ConfirmDialog from "./ConfirmDialog";

type ProjectChatProps = {
  project: Project;
  selectedConversationId: number | null;
  onSelectConversation: (conversationId: number | null) => void;
  onConversationCreated?: (conversationId: number) => void;
  onProjectUpdated?: (project: Project) => void;
  onProjectDeleted?: (projectId: number) => void;
};

export default function ProjectChat({
  project,
  selectedConversationId,
  onSelectConversation,
  onConversationCreated,
  onProjectUpdated,
}: ProjectChatProps) {
  const [conversations, setConversations] = useState<ProjectConversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);

  const loadConversations = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getProjectConversations(project.id);
      setConversations(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to load conversations";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  async function handleCreateConversation(title: string) {
    try {
      const result = await createProjectConversation(project.id, title);
      const newConv: ProjectConversation = {
        chat_id: result.chat_id,
        title: result.title,
      };
      setConversations((prev) => [newConv, ...prev]);
      onSelectConversation(newConv.chat_id);
      onConversationCreated?.(newConv.chat_id);
      setShowCreateModal(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to create conversation";
      setError(message);
    }
  }

  async function handleEditProject(title: string, description: string) {
    try {
      const { updateProject } = await import("@/lib/api");
      await updateProject(project.id, title, description);
      const updatedProject: Project = {
        ...project,
        title,
        description,
      };
      onProjectUpdated?.(updatedProject);
      setShowEditModal(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to update project";
      setError(message);
    }
  }

  function handleNewChat() {
    setShowCreateModal(true);
  }

  return (
    <div className="project-chat-container">
      <div className="project-conversations-header">
        <div className="project-conversations-list">
          {loading ? (
            <div className="project-conversations-loading">
              <span>Loading conversations…</span>
            </div>
          ) : (
            conversations.map((conv) => {
              const isActive = selectedConversationId === conv.chat_id;
              return (
                <div
                  className={`conversation-item ${isActive ? "conversation-item-active" : ""}`}
                  key={conv.chat_id}
                >
                  <button
                    type="button"
                    className="conversation-select"
                    onClick={() => onSelectConversation(conv.chat_id)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <MessageSquarePlus size={16} aria-hidden="true" />
                    <span>{conv.title || "Untitled conversation"}</span>
                  </button>
                </div>
              );
            })
          )}

          {conversations.length === 0 && !loading && (
            <div className="sidebar-empty-state">
              <MessageSquarePlus size={18} aria-hidden="true" />
              <span>No conversations yet.</span>
            </div>
          )}
        </div>

        <button
          type="button"
          className="project-new-chat-button"
          onClick={handleNewChat}
          title="New conversation"
          aria-label="New conversation"
        >
          <Plus size={16} />
          <span>New chat</span>
        </button>
      </div>

      <div className="project-chat-input">
        <div className="project-header-actions">
          <button
            type="button"
            className="icon-button icon-button-subtle"
            onClick={() => setShowEditModal(true)}
            title="Edit project"
            aria-label="Edit project"
          >
            <Edit3 size={16} />
          </button>
        </div>

        <ChatWindow
          key={selectedConversationId ?? `new-${project.id}`}
          chatId={selectedConversationId}
          onChatCreated={(newChatId) => {
            onSelectConversation(newChatId);
            onConversationCreated?.(newChatId);
            void loadConversations();
          }}
        />
      </div>

      <ProjectCreationModal
        open={showCreateModal}
        mode="create"
        onCancel={() => setShowCreateModal(false)}
        onSave={async (title: string) => {
          await handleCreateConversation(title);
        }}
      />

      <ProjectCreationModal
        open={showEditModal}
        mode="edit"
        initialTitle={project.title}
        initialDescription={project.description}
        onCancel={() => setShowEditModal(false)}
        onSave={handleEditProject}
      />
    </div>
  );
}
