"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown,
  LogOut,
  Moon,
  Settings2,
  Sun,
} from "lucide-react";

type ProfileMenuProps = {
  onLogout: () => void;
  variant?: "sidebar" | "header";
};

type StoredUser = {
  name?: string;
  email?: string;
};

type Theme = "dark" | "light";

function getInitials(name: string) {
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("");

  return initials.toUpperCase() || "M";
}

export default function ProfileMenu({
  onLogout,
  variant = "header",
}: ProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("dark");
  const [user, setUser] = useState<StoredUser>({});

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const storedUser = localStorage.getItem("user");
        if (storedUser) setUser(JSON.parse(storedUser) as StoredUser);

        const storedTheme = localStorage.getItem("mygpt-theme");
        const initialTheme: Theme = storedTheme === "light" ? "light" : "dark";
        setTheme(initialTheme);
        document.documentElement.dataset.theme = initialTheme;
      } catch {
        document.documentElement.dataset.theme = "dark";
      }
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  const displayName = user.name || "MyGPT user";
  const displayEmail = user.email || "Personal AI workspace";

  function toggleTheme() {
    const nextTheme: Theme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    localStorage.setItem("mygpt-theme", nextTheme);
  }

  return (
    <div className={`profile-menu profile-menu-${variant}`}>
      <button
        type="button"
        className={`profile-trigger profile-trigger-${variant}`}
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Open profile menu"
      >
        <span className="profile-avatar" aria-hidden="true">
          {getInitials(displayName)}
        </span>
        {variant === "sidebar" && (
          <span className="profile-trigger-copy">
            <strong>{displayName}</strong>
            <small>{displayEmail}</small>
          </span>
        )}
        <ChevronDown
          size={16}
          className={`profile-chevron ${open ? "profile-chevron-open" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="profile-popover" role="menu">
          <div className="profile-popover-heading">
            <span className="profile-avatar profile-avatar-large" aria-hidden="true">
              {getInitials(displayName)}
            </span>
            <div>
              <strong>{displayName}</strong>
              <small>{displayEmail}</small>
            </div>
          </div>

          <div className="profile-menu-divider" />

          <button type="button" className="profile-menu-item" onClick={toggleTheme} role="menuitem">
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            <span>{theme === "dark" ? "Light theme" : "Dark theme"}</span>
          </button>
          <button type="button" className="profile-menu-item profile-menu-item-muted" disabled role="menuitem">
            <Settings2 size={16} />
            <span>Settings coming soon</span>
          </button>
          <button
            type="button"
            className="profile-menu-item profile-menu-item-danger"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            role="menuitem"
          >
            <LogOut size={16} />
            <span>Log out</span>
          </button>
        </div>
      )}
    </div>
  );
}
