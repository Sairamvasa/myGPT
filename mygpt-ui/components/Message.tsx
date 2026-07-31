import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  role: "user" | "assistant";
  content: string;
};

export default function Message({ role, content }: Props) {
  const isUser = role === "user";

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
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}