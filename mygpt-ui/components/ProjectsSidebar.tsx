"use client";

import { useEffect, useState, useCallback } from "react";
import {
  FolderOpen,
  Minus,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import {
  getProjects,
  createProject,
  deleteProject,
  type Project,
} from "@/lib/api";
import ProjectCreationModal from "./ProjectCreationModal";
import ConfirmDialog from "./ConfirmDialog";
import ProfileMenu from "./ProfileMenu";

type ProjectsSidebarProps = {
  isOpen: boolean;
  onClose: () => void;
  selectedProjectId: number | null;
  onSelectProject: (project: Project | null) => void;
  onProjectCreated?: (project: Project) => void;
  onProjectDeleted?: (projectId: number) => void;
  onLogout: () => void;
};

export default function ProjectsSidebar({
  isOpen,
  onClose,
  selectedProjectId,
  onSelectProject,
  onProjectCreated,
  onProjectDeleted,
  onLogout,
}: ProjectsSidebarProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getProjects();
      setProjects(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to load projects";
      setError(message);
      if (message.includes("401") || message.includes("Authentication")) {
        setProjects([]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      void loadProjects();
    }
  }, [isOpen, loadProjects]);

  function handleSelect(project: Project) {
    onSelectProject(project);
    onClose();
  }

  function handleNewProject() {
    setModalOpen(true);
  }

  async function handleCreateProject(title: string, description: string) {
    try {
      const result = await createProject(title, description);
      const newProject: Project = {
        id: result.project_id,
        title: result.title,
        description: result.description,
        user_id: result.user_id,
      };
      setProjects((prev) => [newProject, ...prev]);
      setModalOpen(false);
      onProjectCreated?.(newProject);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to create project";
      setError(message);
    }
  }

  async function handleDeleteProject() {
    if (!pendingDelete) return;

    try {
      await deleteProject(pendingDelete.id);
      setProjects((prev) =>
        prev.filter((p) => p.id !== pendingDelete.id)
      );
      onProjectDeleted?.(pendingDelete.id);
      if (selectedProjectId === pendingDelete.id) {
        onSelectProject(null);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to delete project";
      setError(message);
    } finally {
      setPendingDelete(null);
    }
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
          <div
            className="sidebar-brand"
            style={{ paddingBottom: 4, marginBottom: 12 }}
          >
            <div className="brand-mark" aria-hidden="true">
              <Sparkles size={18} />
            </div>
            <div className="brand-copy">
              <strong>Projects</strong>
              <span>Your AI workspaces</span>
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

          <button
            type="button"
            className="sidebar-new-chat"
            onClick={handleNewProject}
          >
            <Plus size={18} />
            <span>New project</span>
          </button>
        </div>

        {error && (
          <div className="sidebar-error" role="alert">
            {error}
          </div>
        )}

        <div className="sidebar-section-label">
          <span>Your projects</span>
          <span className="sidebar-count">{projects.length}</span>
        </div>

        <nav
          className="conversation-list"
          aria-label="Projects"
        >
          {loading ? (
            <div className="sidebar-loading">
              <div className="sidebar-skeleton" />
              <div className="sidebar-skeleton sidebar-skeleton-short" />
              <div className="sidebar-skeleton sidebar-skeleton-short sidebar-skeleton-wider" />
            </div>
          ) : projects.length === 0 ? (
            <div className="sidebar-empty-state">
              <FolderOpen size={20} aria-hidden="true" />
              <span>No projects yet. Create one to get started.</span>
            </div>
          ) : (
            projects.map((project) => {
              const isActive = selectedProjectId === project.id;
              const preview = project.description.length > 60
                ? project.description.slice(0, 60) + "…"
                : project.description || "No description";

              return (
                <div
                  className={`conversation-item ${isActive ? "conversation-item-active" : ""}`}
                  key={project.id}
                >
                  <button
                    type="button"
                    className="conversation-select"
                    onClick={() => handleSelect(project)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <FolderOpen size={16} aria-hidden="true" />
                    <span className="conversation-title">
                      {project.title || "Untitled project"}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="conversation-action"
                    onClick={(event) => {
                      event.stopPropagation();
                      setPendingDelete(project);
                    }}
                    aria-label={`Delete ${project.title}`}
                    title="Delete project"
                  >
                    <Minus size={17} aria-hidden="true" />
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

      <ProjectCreationModal
        open={modalOpen}
        mode="create"
        onCancel={() => setModalOpen(false)}
        onSave={handleCreateProject}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete project?"
        description={`This will permanently remove "${pendingDelete?.title || "this project"}" and all its conversations and files.`}
        onCancel={() => setPendingDelete(null)}
        onConfirm={handleDeleteProject}
      />
    </>
  );
}
