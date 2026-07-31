import Message from "./Message";
import { ChatMessage } from "./ChatWindow";

type Props = {
  messages?: ChatMessage[];
};

export default function MessageList({ messages = [] }: Props) {
  return (
    <div className="flex-1 overflow-y-auto p-6">
      {messages.map((msg, index) => (
        <Message
          key={index}
          role={msg.role}
          content={msg.content}
        />
      ))}
    </div>
  );
}