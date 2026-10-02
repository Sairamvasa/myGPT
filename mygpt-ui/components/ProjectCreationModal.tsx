"use client";

import { useState } from "react";
import { X } from "lucide-react";

type ProjectCreationModalProps = {
  open: boolean;
  mode?: "create" | "edit";
  initialTitle?: string;
  initialDescription?: string;
  projectId?: number | null;
  onCancel: () => void;
  onSave: (title: string, description: string) => Promise<void>;
};

export default function ProjectCreationModal({
  open,
  mode = "create",
  initialTitle = "",
  initialDescription = "",
  onCancel,
  onSave,
}: ProjectCreationModalProps) {
  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState(initialDescription);
  const [isSaving, setIsSaving] = useState(false);

  const isEditMode = mode === "edit";
  const titleValid = title.trim().length > 0 && title.length <= 200;

  const handleSave = async () => {
    if (!titleValid || isSaving) return;

    setIsSaving(true);
    try {
      await onSave(title.trim(), description.trim());
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSave();
    }
  };

  if (!open) return null;

  return (
    <>
      <div
        className="confirm-backdrop"
        role="presentation"
        onMouseDown={(event) => {
          if (event.currentTarget === event.target) onCancel();
        }}
      />

      <div
        className="project-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-modal-title"
      >
        <div className="project-modal-header">
          <h2 id="project-modal-title" className="project-modal-title">
            {isEditMode ? "Edit project" : "Create project"}
          </h2>
          <button
            type="button"
            className="icon-button icon-button-subtle"
            onClick={onCancel}
            aria-label="Close"
            title="Close"
            disabled={isSaving}
          >
            <X size={18} />
          </button>
        </div>

        <div className="project-modal-body">
          <div className="form-group">
            <label htmlFor="project-title-input" className="form-label required">
              Title
            </label>
            <input
              id="project-title-input"
              type="text"
              className={`form-input ${!titleValid ? "form-input-error" : ""}`}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Project name"
              maxLength={200}
              autoFocus
            />
            {!titleValid && title.length > 0 && (
              <span className="form-error-text">
                {title.length > 200
                  ? `Maximum 200 characters (${title.length}/200)`
                  : "Title is required"}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="project-desc-input" className="form-label">
              Description
            </label>
            <textarea
              id="project-desc-input"
              className="form-textarea"
              value={description}
              onChange={(event) => setDescription(event.target.value.slice(0, 2000))}
              placeholder="What is this project about? (optional)"
              maxLength={2000}
              onKeyDown={handleKeyDown}
              rows={4}
            />
            {description.length >= 1900 && (
              <span className="form-hint">
                {description.length}/2000 characters
              </span>
            )}
          </div>
        </div>

        <div className="project-modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onCancel}
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            type="button"
            className="sidebar-new-chat"
            onClick={handleSave}
            disabled={!titleValid || isSaving}
          >
            {isSaving
              ? (isEditMode ? "Saving…" : "Creating…")
              : (isEditMode ? "Save changes" : "Create project")}
          </button>
        </div>
      </div>
    </>
  );
}
