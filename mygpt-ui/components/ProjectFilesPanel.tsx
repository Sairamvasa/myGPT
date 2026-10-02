"use client";

import { useState, useEffect, useCallback } from "react";
import {
  FileText,
  Download,
  Trash2,
  Upload,
  X,
  FileCode,
  FileImage,
  AlertCircle,
  Loader2,
} from "lucide-react";
import {
  uploadProjectFile,
  getProjectFiles,
  downloadProjectFile,
  deleteProjectFile,
  type ProjectFileRecord,
} from "@/lib/api";
import ConfirmDialog from "./ConfirmDialog";

type ProjectFilesPanelProps = {
  projectId: number;
  refreshTrigger?: number;
  onFileDeleted?: (fileId: number) => void;
  onFileUploaded?: (file: ProjectFileRecord) => void;
};

function getFileIcon(fileType: string): React.ReactNode {
  const ext = fileType.toLowerCase();

  if (ext === "pdf") {
    return <FileText size={18} className="file-icon file-icon-pdf" />;
  }
  if (["py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "rb", "go", "rs", "php", "swift", "kt", "sql", "sh", "html", "css", "json", "md", "txt", "yaml", "yml", "xml", "csv"].includes(ext)) {
    return <FileCode size={18} className="file-icon file-icon-code" />;
  }
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) {
    return <FileImage size={18} className="file-icon file-icon-image" />;
  }
  return <FileText size={18} className="file-icon file-icon-default" />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

const SUPPORTED_EXTENSIONS = new Set([
  "pdf", "txt", "md", "markdown", "rst",
  "py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "hpp",
  "rb", "go", "rs", "php", "swift", "kt", "scala",
  "sh", "bash", "zsh",
  "html", "htm", "css", "scss", "sass", "less",
  "json", "jsonc", "yaml", "yml", "toml", "ini", "cfg", "conf",
  "xml", "csv", "tsv", "sql",
  "log",
]);

export default function ProjectFilesPanel({
  projectId,
  refreshTrigger = 0,
  onFileDeleted,
  onFileUploaded,
}: ProjectFilesPanelProps) {
  const [files, setFiles] = useState<ProjectFileRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadingFiles, setUploadingFiles] = useState<
    { file: File; progress: number }[]
  >([]);
  const [pendingDelete, setPendingDelete] = useState<ProjectFileRecord | null>(null);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getProjectFiles(projectId);
      setFiles(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to load files";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadFiles();
  }, [loadFiles, refreshTrigger]);

  function validateFile(file: File): string | null {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !SUPPORTED_EXTENSIONS.has(ext)) {
      return `Unsupported file type: .${ext || "unknown"}`;
    }
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      return `File too large. Maximum size is 50 MB.`;
    }
    return null;
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length === 0) return;

    event.target.value = "";

    const validFiles: File[] = [];
    for (const file of selectedFiles) {
      const errorMsg = validateFile(file);
      if (errorMsg) {
        setError(errorMsg);
        return;
      }
      validFiles.push(file);
    }

    setUploadingFiles(
      validFiles.map((f) => ({ file: f, progress: 0 }))
    );
    setError("");

    for (let i = 0; i < validFiles.length; i++) {
      const file = validFiles[i];
      let uploadFailed = false;

      try {
        const result = await uploadProjectFile(
          projectId,
          file,
          (percent) => {
            setUploadingFiles((prev) =>
              prev.map((uf, idx) =>
                idx === i ? { ...uf, progress: percent } : uf
              )
            );
          }
        );

        const newFileRecord: ProjectFileRecord = {
          id: result.file_id,
          project_id: projectId,
          user_id: 0,
          filename: result.filename,
          file_type: result.file_type,
          file_size: result.file_size,
          created_at: new Date().toISOString(),
        };

        setFiles((prev) => [newFileRecord, ...prev]);
        onFileUploaded?.(newFileRecord);
      } catch (error) {
        uploadFailed = true;
        const message =
          error instanceof Error ? error.message : "Upload failed";
        setError(`Failed to upload ${file.name}: ${message}`);
      } finally {
        setUploadingFiles((prev) =>
          prev.filter((uf) => uf.file !== file)
        );
      }

      if (uploadFailed) {
        void loadFiles();
        return;
      }
    }

    void loadFiles();
  }

  async function handleDownload(file: ProjectFileRecord) {
    try {
      const blob = await downloadProjectFile(projectId, file.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Download failed";
      setError(message);
    }
  }

  function handleDelete(file: ProjectFileRecord) {
    setPendingDelete(file);
  }

  async function confirmDelete(file: ProjectFileRecord) {
    try {
      await deleteProjectFile(projectId, file.id);
      setFiles((prev) => prev.filter((f) => f.id !== file.id));
      onFileDeleted?.(file.id);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to delete file";
      setError(message);
    } finally {
      setPendingDelete(null);
    }
   }

  return (
    <div className="project-files-panel">
      <div className="project-files-header">
        <h3 className="project-files-title">Project files</h3>
        <label
          className="project-file-upload-button"
          title="Upload file"
          aria-label="Upload file"
        >
          <Upload size={16} aria-hidden="true" />
          <span>Upload</span>
          <input
            type="file"
            className="hidden"
            multiple
            onChange={handleFileChange}
            accept=".pdf,.txt,.md,.markdown,.rst,.py,.js,.ts,.tsx,.jsx,.java,.c,.cpp,.h,.hpp,.rb,.go,.rs,.php,.swift,.kt,.scala,.sh,.bash,.zsh,.html,.htm,.css,.scss,.sass,.less,.json,.jsonc,.yaml,.yml,.toml,.ini,.cfg,.conf,.xml,.csv,.tsv,.sql,.log"
          />
        </label>
      </div>

      {error && (
        <div className="project-files-error" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {uploadingFiles.length > 0 && (
        <div className="project-upload-progress-list">
          {uploadingFiles.map((uf) => (
            <div key={uf.file.name} className="project-upload-item">
              <div className="project-upload-name">
                <FileText size={14} aria-hidden="true" />
                <span>{uf.file.name}</span>
              </div>
              <div className="project-upload-progress-bar">
                <div
                  className="project-upload-progress-fill"
                  style={{ width: `${uf.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="project-files-loading">
          <Loader2 size={20} className="animate-spin" aria-hidden="true" />
          <span>Loading files...</span>
        </div>
      ) : files.length === 0 && uploadingFiles.length === 0 ? (
        <div className="project-files-empty">
          <FileText size={32} aria-hidden="true" />
          <p>No files uploaded yet.</p>
          <p className="project-files-empty-hint">
            Upload PDF, text, or code files to give this project context.
          </p>
        </div>
      ) : (
        <div className="project-files-list">
          {files.map((file) => (
            <div className="project-file-item" key={file.id}>
              <div className="project-file-info">
                <span className="project-file-icon">
                  {getFileIcon(file.file_type)}
                </span>
                <div className="project-file-details">
                  <span className="project-file-name" title={file.filename}>
                    {file.filename}
                  </span>
                  <span className="project-file-meta">
                    {formatFileSize(file.file_size)} · {file.file_type.toUpperCase()}
                  </span>
                </div>
              </div>

              <div className="project-file-actions">
                <button
                  type="button"
                  className="icon-button icon-button-subtle"
                  onClick={() => handleDownload(file)}
                  title="Download"
                  aria-label={`Download ${file.filename}`}
                >
                  <Download size={15} />
                </button>
                <button
                  type="button"
                  className="icon-button icon-button-subtle"
                  onClick={() => handleDelete(file)}
                  title="Delete"
                  aria-label={`Delete ${file.filename}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDelete && (
        <ConfirmDialog
          open={pendingDelete !== null}
          title="Delete file?"
          description={`This will permanently remove "${pendingDelete.filename}".`}
          confirmLabel="Delete file"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            if (pendingDelete) confirmDelete(pendingDelete);
          }}
        />
      )}
    </div>
  );
}
