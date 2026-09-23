"use client";

import {
  Bug,
  Code2,
  FileSearch,
  Lightbulb,
  Sparkles,
} from "lucide-react";

const prompts = [
  {
    label: "Explain this code",
    description: "Break down a function or snippet step by step.",
    icon: Code2,
    prompt: "Explain this code and how it works step by step.",
  },
  {
    label: "Find bugs in my project",
    description: "Track down errors and suggest practical fixes.",
    icon: Bug,
    prompt: "Help me find bugs in my project and suggest fixes.",
  },
  {
    label: "Analyze this file",
    description: "Upload a file and get a focused summary or review.",
    icon: FileSearch,
    prompt: "Analyze the file I uploaded and summarize the key points.",
  },
  {
    label: "Help me build a project",
    description: "Turn an idea into a clear technical plan.",
    icon: Lightbulb,
    prompt: "Help me plan and build a project from this idea.",
  },
];

function sendQuickPrompt(prompt: string) {
  window.dispatchEvent(
    new CustomEvent("mygpt-quick-prompt", {
      detail: prompt,
    })
  );
}

export default function ConversationEmptyState() {
  return (
    <section className="conversation-empty-state" aria-labelledby="empty-state-heading">
      <div className="empty-state-intro">
        <div className="empty-state-icon" aria-hidden="true">
          <Sparkles size={24} />
        </div>
        <p className="conversation-empty-eyebrow">Your personal AI workspace</p>
        <h2 className="empty-state-title" id="empty-state-heading">
          What are you working on today?
        </h2>
        <p className="empty-state-description">
          Ask questions, explore ideas, review files, or build something with MyGPT.
        </p>
      </div>

      <div className="quick-prompt-grid">
        {prompts.map(({ label, description, icon: Icon, prompt }) => (
          <button
            type="button"
            className="quick-prompt-card"
            key={label}
            onClick={() => sendQuickPrompt(prompt)}
          >
            <span className="quick-prompt-icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            <span className="quick-prompt-copy">
              <strong className="quick-prompt-label">{label}</strong>
              <small className="quick-prompt-description">{description}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
