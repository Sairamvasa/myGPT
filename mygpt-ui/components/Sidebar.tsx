"use client";

type Conversation = {
  chat_id: number;
  title: string;
};

type SidebarProps = {
  conversations: Conversation[];
  activeChatId: number | null;
  onNewChat: () => void;
  onSelectChat: (chatId: number) => void;
  onDeleteChat: (chatId: number) => void;
};

export default function Sidebar({
  conversations,
  activeChatId,
  onNewChat,
  onSelectChat,
  onDeleteChat,
}: SidebarProps) {
  return (
    <div className="w-72 h-screen bg-black text-white p-5">

      <h1 className="text-3xl font-bold">
        🤖 MyGPT
      </h1>

      <button
        onClick={onNewChat}
        className="mt-6 bg-zinc-800 w-full rounded-xl p-3 hover:bg-zinc-700"
      >
        + New Chat
      </button>

      <div className="mt-6">
        <p className="text-sm text-gray-400 mb-3">
          Recent Chats
        </p>

        {conversations.map((chat) => (
          <div
            key={chat.chat_id}
            className={`flex items-center rounded-lg mb-1 ${
              activeChatId === chat.chat_id
                ? "bg-zinc-700"
                : "hover:bg-zinc-800"
            }`}
          >
            {/* Chat title */}
            <button
              onClick={() =>
                onSelectChat(chat.chat_id)
              }
              className="flex-1 text-left p-3 truncate"
            >
              {chat.title}
            </button>

            {/* Delete */}
            <button
              onClick={(e) => {
                e.stopPropagation();

                const confirmed = window.confirm(
                  `Delete "${chat.title}"?`
                );

                if (confirmed) {
                  onDeleteChat(chat.chat_id);
                }
              }}
              className="px-3 py-3 text-gray-400 hover:text-red-500"
              title="Delete chat"
            >
              🗑️
            </button>
          </div>
        ))}
      </div>

    </div>
  );
}