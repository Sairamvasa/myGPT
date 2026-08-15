"use client";

import { useEffect, useState } from "react";

import Sidebar from "@/components/Sidebar";
import ChatWindow from "@/components/ChatWindow";

import {
  createNewChat,
  getConversations,
  deleteConversation,
  loginUser,
  registerUser,
  getToken,
  logoutUser,
} from "@/lib/api";

type Conversation = {
  chat_id: number;
  title: string;
};

export default function Home() {
  const [chatId, setChatId] = useState<number | null>(null);
  const [conversations, setConversations] =
    useState<Conversation[]>([]);

  // ==============================
  // AUTH STATE
  // ==============================

  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  const [showRegister, setShowRegister] = useState(false);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  // ==============================
  // CHECK LOGIN
  // ==============================

  useEffect(() => {
    const token = getToken();

    if (token) {
      setIsLoggedIn(true);
    }

    setCheckingAuth(false);
  }, []);

  // ==============================
  // LOAD CONVERSATIONS
  // ==============================

  async function loadConversations() {
    try {
      const data = await getConversations();

      setConversations(data);

      if (chatId === null && data.length > 0) {
        setChatId(data[0].chat_id);
      }
    } catch (error) {
      console.error(
        "Failed to load conversations:",
        error
      );
    }
  }

  useEffect(() => {
    if (isLoggedIn) {
      loadConversations();
    }
  }, [isLoggedIn]);

  // ==============================
  // LOGIN
  // ==============================

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();

    setAuthError("");
    setAuthLoading(true);

    try {
      await loginUser(email, password);

      setIsLoggedIn(true);

      setEmail("");
      setPassword("");
    } catch (error: any) {
      setAuthError(
        error.message || "Login failed"
      );
    } finally {
      setAuthLoading(false);
    }
  }

  // ==============================
  // REGISTER
  // ==============================

  async function handleRegister(
    e: React.FormEvent
  ) {
    e.preventDefault();

    setAuthError("");
    setAuthLoading(true);

    try {
      await registerUser(
        name,
        email,
        password
      );

      // Registration successful
      // Go to login screen
      setShowRegister(false);

      setName("");
      setPassword("");

      setAuthError(
        "Registration successful! Please login."
      );
    } catch (error: any) {
      setAuthError(
        error.message || "Registration failed"
      );
    } finally {
      setAuthLoading(false);
    }
  }

  // ==============================
  // LOGOUT
  // ==============================

  function handleLogout() {
    logoutUser();

    setIsLoggedIn(false);
    setChatId(null);
    setConversations([]);
  }

  // ==============================
  // NEW CHAT
  // ==============================

  async function handleNewChat() {
    // Immediately set to clean new session
    setChatId(null);
    try {
      const newChat = await createNewChat();
      setChatId(newChat.chat_id);
      await loadConversations();
    } catch (error) {
      console.warn("New chat pre-creation deferred to first message:", error);
    }
  }

  // ==============================
  // SELECT CHAT
  // ==============================

  function handleSelectChat(id: number) {
    setChatId(id);
  }

  // ==============================
  // DELETE CHAT
  // ==============================

  async function handleDeleteChat(id: number) {
    try {
      await deleteConversation(id);

      const remainingChats =
        conversations.filter(
          (chat) => chat.chat_id !== id
        );

      setConversations(remainingChats);

      if (chatId === id) {
        if (remainingChats.length > 0) {
          setChatId(
            remainingChats[0].chat_id
          );
        } else {
          setChatId(null);
        }
      }
    } catch (error) {
      console.error(
        "Failed to delete conversation:",
        error
      );

      alert("Unable to delete chat.");
    }
  }

  // ==============================
  // CHECKING AUTH
  // ==============================

  if (checkingAuth) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#202123] text-white">
        <div className="text-lg">
          Loading MyGPT...
        </div>
      </div>
    );
  }

  // ==============================
  // LOGIN / REGISTER SCREEN
  // ==============================

  if (!isLoggedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#202123] px-4 text-white">
        <div className="w-full max-w-md rounded-2xl bg-[#343541] p-8 shadow-2xl">

          {/* LOGO */}
          <div className="mb-8 text-center">
            <div className="text-4xl">
              🤖
            </div>

            <h1 className="mt-2 text-3xl font-bold">
              MyGPT
            </h1>

            <p className="mt-2 text-gray-400">
              Your personal AI assistant
            </p>
          </div>

          {/* TITLE */}
          <h2 className="mb-6 text-center text-xl font-semibold">
            {showRegister
              ? "Create your account"
              : "Welcome back"}
          </h2>

          {/* ERROR / SUCCESS */}
          {authError && (
            <div className="mb-4 rounded-lg bg-[#444654] p-3 text-sm text-gray-200">
              {authError}
            </div>
          )}

          {/* REGISTER */}
          {showRegister ? (
            <form
              onSubmit={handleRegister}
              className="space-y-4"
            >

              <input
                type="text"
                placeholder="Name"
                value={name}
                onChange={(e) =>
                  setName(e.target.value)
                }
                required
                className="w-full rounded-lg bg-[#202123] px-4 py-3 text-white outline-none focus:ring-2 focus:ring-blue-500"
              />

              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) =>
                  setEmail(e.target.value)
                }
                required
                className="w-full rounded-lg bg-[#202123] px-4 py-3 text-white outline-none focus:ring-2 focus:ring-blue-500"
              />

              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) =>
                  setPassword(e.target.value)
                }
                required
                className="w-full rounded-lg bg-[#202123] px-4 py-3 text-white outline-none focus:ring-2 focus:ring-blue-500"
              />

              <button
                type="submit"
                disabled={authLoading}
                className="w-full rounded-lg bg-blue-600 py-3 font-semibold hover:bg-blue-700 disabled:opacity-50"
              >
                {authLoading
                  ? "Registering..."
                  : "Register"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowRegister(false);
                  setAuthError("");
                }}
                className="w-full py-2 text-sm text-gray-400 hover:text-white"
              >
                Already have an account? Login
              </button>

            </form>
          ) : (
            /* LOGIN */
            <form
              onSubmit={handleLogin}
              className="space-y-4"
            >

              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) =>
                  setEmail(e.target.value)
                }
                required
                className="w-full rounded-lg bg-[#202123] px-4 py-3 text-white outline-none focus:ring-2 focus:ring-blue-500"
              />

              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) =>
                  setPassword(e.target.value)
                }
                required
                className="w-full rounded-lg bg-[#202123] px-4 py-3 text-white outline-none focus:ring-2 focus:ring-blue-500"
              />

              <button
                type="submit"
                disabled={authLoading}
                className="w-full rounded-lg bg-blue-600 py-3 font-semibold hover:bg-blue-700 disabled:opacity-50"
              >
                {authLoading
                  ? "Logging in..."
                  : "Login"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowRegister(true);
                  setAuthError("");
                }}
                className="w-full py-2 text-sm text-gray-400 hover:text-white"
              >
                Don't have an account? Register
              </button>

            </form>
          )}
        </div>
      </div>
    );
  }

  // ==============================
  // MAIN CHAT UI
  // ==============================

  return (
    <div className="relative flex h-screen overflow-hidden">

      <Sidebar
        conversations={conversations}
        activeChatId={chatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
      />

      <ChatWindow
        chatId={chatId}
        onChatCreated={(newId) => {
          setChatId(newId);
          loadConversations();
        }}
      />

      {/* LOGOUT BUTTON */}
      <button
        onClick={handleLogout}
        className="absolute right-3 top-3 z-50 rounded-lg bg-[#343541] px-3 py-2 text-sm text-white shadow hover:bg-[#444654]"
      >
        Logout
      </button>

    </div>
  );
}