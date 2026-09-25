"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Bot, Check, Copy, UserRound } from "lucide-react";

type Props = {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
};

const getTextContent = (node: unknown): string => {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(getTextContent).join("");
  if (node && typeof node === "object" && "props" in node) {
    const props = (node as { props?: { children?: unknown } }).props;
    if (props && props.children !== undefined) {
      return getTextContent(props.children);
    }
  }
  return "";
};

function getCodeLanguage(node: unknown): string | null {
  if (node && typeof node === "object" && "props" in node) {
    const props = (node as { props?: { className?: unknown } }).props;
    const className = props?.className;

    if (typeof className === "string") {
      return className.match(/(?:^|\s)language-([\w+-]+)/)?.[1] ?? null;
    }
  }

  return null;
}

type CopyButtonProps = {
  value: string;
  className?: string;
};

function CopyButton({ value, className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);

      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = window.setTimeout(() => {
        setCopied(false);
      }, 1600);
    } catch (error) {
      console.error("Failed to copy content:", error);
    }
  }

  const Icon = copied ? Check : Copy;

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={`message-copy-button ${className} ${copied ? "is-copied" : ""}`}
      title={copied ? "Copied" : "Copy"}
      aria-label={copied ? "Copied" : "Copy"}
    >
      <Icon size={14} aria-hidden="true" />
      <span>{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

export default function Message({ role, content, isStreaming = false }: Props) {
  const isUser = role === "user";

  return (
    <article className={`message-row ${isUser ? "message-row-user" : "message-row-assistant"}`}>
      <div className={`message-avatar ${isUser ? "message-avatar-user" : "message-avatar-assistant"}`} aria-hidden="true">
        {isUser ? <UserRound size={16} /> : <Bot size={17} />}
      </div>

      <div className="message-body">
        <div className="message-meta">{isUser ? "You" : "MyGPT"}</div>
        <div className="message-content">
          {isUser ? (
            <p className="user-message-text">{content}</p>
          ) : (
            <div className="ai-message">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{
                  pre({ children, ...props }) {
                    const code = getTextContent(children).replace(/\n$/, "");
                    const language = getCodeLanguage(children);

                    return (
                      <div className="code-block-wrapper">
                        <div className="code-block-toolbar">
                          <span className="code-block-language">
                            {language || "Code"}
                          </span>
                          <CopyButton value={code} className="code-copy-button" />
                        </div>

                        <pre {...props} className="code-block">
                          {children}
                        </pre>
                      </div>
                    );
                  },
                  code({ className, children, ...props }) {
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {content}
              </ReactMarkdown>
              {isStreaming && (
                <span
                  className="streaming-cursor"
                  aria-hidden="true"
                />
              )}
            </div>
          )}
        </div>

        {content && <div className="message-actions"><CopyButton value={content} /></div>}
      </div>
    </article>
  );
}
