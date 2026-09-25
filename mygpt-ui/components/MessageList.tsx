import Message from "./Message";
import { ChatMessage } from "./ChatWindow";

type Props = {
  messages?: ChatMessage[];
};

export default function MessageList({ messages = [] }: Props) {
  return (
    <div className="message-list">
      {messages.map((msg, index) => (
        <Message
          key={msg.id ?? `${msg.role}-${index}`}
          role={msg.role}
          content={msg.content}
          isStreaming={msg.isStreaming}
        />
      ))}
    </div>
  );
}
