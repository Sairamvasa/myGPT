"use client";

import { useCallback, useEffect, useState } from "react";

import AppShell from "@/components/AppShell";

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

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

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

    const timer = window.setTimeout(() => {
      setIsLoggedIn(Boolean(token));
      setCheckingAuth(false);
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  // ==============================
  // LOAD CONVERSATIONS
  // ==============================

  const loadConversations = useCallback(async () => {
    try {
      const data = await getConversations();

      setConversations(data);

      setChatId((currentChatId) =>
        currentChatId === null && data.length > 0
          ? data[0].chat_id
          : currentChatId
      );
    } catch (error) {
      console.error("Failed to load conversations:", error);
    }
  }, []);

  useEffect(() => {
    if (isLoggedIn) {
      void Promise.resolve().then(loadConversations);
    }
  }, [isLoggedIn, loadConversations]);

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
    } catch (error: unknown) {
      setAuthError(getErrorMessage(error, "Login failed"));
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

      // Registration now returns access_token and logs user in automatically
      setIsLoggedIn(true);

      setName("");
      setEmail("");
      setPassword("");
      setShowRegister(false);
    } catch (error: unknown) {
      setAuthError(getErrorMessage(error, "Registration failed"));
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
      <div className="auth-loading-screen">
        <div className="auth-loading-mark" aria-hidden="true">✦</div>
        <div className="auth-loading-label">
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
      <div className="auth-screen">
        <div className="auth-card">

          {/* LOGO */}
          <div className="auth-brand">
            <div className="auth-brand-mark" aria-hidden="true">
              🤖
            </div>

            <h1>
              MyGPT
            </h1>

            <p>
              Your personal AI assistant
            </p>
          </div>

          {/* TITLE */}
          <h2 className="auth-card-title">
            {showRegister
              ? "Create your account"
              : "Welcome back"}
          </h2>

          {/* ERROR / SUCCESS */}
          {authError && (
            <div className="auth-feedback">
              {authError}
            </div>
          )}

          {/* REGISTER */}
          {showRegister ? (
            <form
              onSubmit={handleRegister}
              className="auth-form"
            >

              <input
                type="text"
                placeholder="Name"
                value={name}
                onChange={(e) =>
                  setName(e.target.value)
                }
                required
                className="auth-input"
              />

              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) =>
                  setEmail(e.target.value)
                }
                required
                className="auth-input"
              />

              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) =>
                  setPassword(e.target.value)
                }
                required
                minLength={8}
                className="auth-input"
              />

              <button
                type="submit"
                disabled={authLoading}
                className="auth-submit-button"
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
                className="auth-switch-button"
              >
                Already have an account? Login
              </button>

            </form>
          ) : (
            /* LOGIN */
            <form
              onSubmit={handleLogin}
              className="auth-form"
            >

              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) =>
                  setEmail(e.target.value)
                }
                required
                className="auth-input"
              />

              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) =>
                  setPassword(e.target.value)
                }
                required
                className="auth-input"
              />

              <button
                type="submit"
                disabled={authLoading}
                className="auth-submit-button"
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
                className="auth-switch-button"
              >
                Don&apos;t have an account? Register
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
    <AppShell
      conversations={conversations}
      activeChatId={chatId}
      onNewChat={handleNewChat}
      onSelectChat={handleSelectChat}
      onDeleteChat={handleDeleteChat}
      onChatCreated={(newId) => {
        setChatId(newId);
        loadConversations();
      }}
      onLogout={handleLogout}
    />
  );
}
