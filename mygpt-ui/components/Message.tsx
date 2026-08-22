"use client";

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
                pre({ children, ...props }) {
                  const code = getTextContent(children).replace(/\n$/, "");

                  return (
                    <div className="relative">
                      <button
                        onClick={() => navigator.clipboard.writeText(code)}
                        className="absolute top-2 right-2 z-10 px-2 py-1 rounded bg-gray-700 text-gray-200 text-xs hover:bg-gray-600 transition"
                        title="Copy code"
                        aria-label="Copy code"
                      >
                        Copy
                      </button>

                      <pre
                        {...props}
                        className="bg-gray-900 rounded-lg p-4 pt-10 overflow-x-auto text-sm leading-relaxed"
                      >
                        {children}
                      </pre>
                    </div>
                  );
                },
                code({ className, children, ...props }) {
                  const isCodeBlock = !!className;

                  if (!isCodeBlock) {
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  }

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
          </div>
        )}
      </div>
    </div>
  );
}
