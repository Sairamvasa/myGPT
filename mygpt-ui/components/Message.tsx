"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

type Props = {
  role: "user" | "assistant";
  content: string;
};

export default function Message({ role, content }: Props) {
  const isUser = role === "user";

  const getTextContent = (node: unknown): string => {
    if (typeof node === "string") return node;
    if (Array.isArray(node)) return node.map(getTextContent).join("");
    if (node && typeof node === "object" && "props" in node) {
      const props = (node as { props?: { children?: unknown } }).props;
      if (props && props.children !== undefined) {
        return getTextContent(props.children);
      }
    }
    return "";
  };

  return (
    <div
      className={`mb-4 flex ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      <div
        className={`max-w-[80%] p-4 rounded-lg ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-gray-700 text-white"
        }`}
      >
        {isUser ? (
          content
        ) : (
          <div className="ai-message">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                code({ className, children, ...props }) {
                  const [copied, setCopied] = useState(false);

                  const isCodeBlock = !!className;

                  const code = getTextContent(children).replace(/\n$/, "");

                  const handleCopy = async () => {
                    await navigator.clipboard.writeText(code);

                    setCopied(true);

                    setTimeout(() => {
                      setCopied(false);
                    }, 1500);
                  };

                  if (!isCodeBlock) {
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  }

                  return (
                    <div className="relative">
                      <button
                        onClick={handleCopy}
                        className="absolute top-2 right-2 z-10 w-9 h-9 rounded-full bg-gray-200 text-gray-700 flex items-center justify-center hover:bg-white transition"
                        title={copied ? "Copied" : "Copy code"}
                        aria-label="Copy code"
                      >
                        {copied ? "✓" : "▣"}
                      </button>

                      <code className={className} {...props}>
                        {children}
                      </code>
                    </div>
                  );
                },
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}