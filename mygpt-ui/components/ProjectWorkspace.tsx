"use client";

import { useState, useEffect } from "react";
import { PanelLeft, PanelRight } from "lucide-react";
import ProjectFilesPanel from "./ProjectFilesPanel";
import ProjectChat from "./ProjectChat";
import type { Project } from "@/lib/api";

type ProjectWorkspaceProps = {
  selectedProject: Project | null;
  selectedConversationId: number | null;
  onSelectConversation: (conversationId: number | null) => void;
  onProjectUpdated?: (project: Project) => void;
  onProjectDeleted?: (projectId: number) => void;
};

export default function ProjectWorkspace({
  selectedProject,
  selectedConversationId,
  onSelectConversation,
  onProjectUpdated,
  onProjectDeleted,
}: ProjectWorkspaceProps) {
  const [filesPanelOpen, setFilesPanelOpen] = useState(true);
  const [refreshFiles, setRefreshFiles] = useState(0);

  const [showFiles, setShowFiles] = useState(true);

  useEffect(() => {
    const isMobile = window.matchMedia("(max-width: 767px)").matches;
    setShowFiles(isMobile ? false : true);

    const mq = window.matchMedia("(max-width: 767px)");
    const handler = (e: MediaQueryListEvent) => setShowFiles(!e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const toggleFilesPanel = () => {
    setShowFiles((prev) => !prev);
  };

  if (!selectedProject) {
    return (
      <div className="project-workspace-empty">
        <div className="project-workspace-empty-content">
          <div className="project-workspace-empty-icon" aria-hidden="true">
            ?
          </div>
          <h2>Select a project</h2>
          <p>Choose a project from the sidebar or create a new one to get started.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="project-workspace">
      <div className={`project-files-sidebar ${showFiles ? "show" : ""}`}>
        <ProjectFilesPanel
          key={`${selectedProject.id}-${refreshFiles}`}
          projectId={selectedProject.id}
          onFileDeleted={() => setRefreshFiles((prev) => prev + 1)}
          onFileUploaded={() => setRefreshFiles((prev) => prev + 1)}
        />
      </div>

      <div className="project-workspace-main">
        <div className="project-mobile-header">
          <button
            type="button"
            className="project-toggle-files-button"
            onClick={toggleFilesPanel}
            aria-label={showFiles ? "Hide files" : "Show files"}
            title={showFiles ? "Hide files" : "Show files"}
          >
            {showFiles ? <PanelLeft size={16} /> : <PanelRight size={16} />}
            <span>{showFiles ? "Hide files" : "Show files"}</span>
          </button>

          <div className="project-mobile-title">
            <span className="project-mobile-project-name">
              {selectedProject.title}
            </span>
          </div>
        </div>

        <ProjectChat
          project={selectedProject}
          selectedConversationId={selectedConversationId}
          onSelectConversation={onSelectConversation}
          onProjectUpdated={onProjectUpdated}
          onProjectDeleted={onProjectDeleted}
        />
      </div>
    </div>
  );
}
