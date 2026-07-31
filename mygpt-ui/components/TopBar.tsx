import { Settings } from "lucide-react";

export default function TopBar() {
  return (
    <div className="h-16 border-b border-gray-700 flex items-center justify-between px-6">

      <h1 className="text-xl font-bold">
        🤖 MyGPT
      </h1>

      <button>
        <Settings size={22} />
      </button>

    </div>
  );
}