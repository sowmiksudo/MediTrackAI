import React, { createContext, useContext, useEffect, useState } from "react";
import {
  apiFetch,
  getStoredProfileId,
  getStoredToken,
  setStoredProfileId,
  setStoredToken,
} from "@/lib/api";

export interface PatientProfile {
  id: string;
  display_name: string;
  relationship: string;
  sex?: string | null;
  date_of_birth?: string | null;
  chronic_conditions: string[];
  allergies: string[];
}

export interface AuthUser {
  id: string;
  full_name: string;
  email?: string | null;
  phone_e164?: string | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  profiles: PatientProfile[];
  activeProfile: PatientProfile | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  register: (payload: {
    full_name: string;
    email?: string;
    phone_e164?: string;
    password: string;
    accepted_cloud_ai_processing: boolean;
  }) => Promise<void>;
  logout: () => void;
  switchProfile: (profileId: string) => void;
  refreshProfiles: () => Promise<void>;
  createProfile: (payload: {
    display_name: string;
    relationship: string;
    sex?: string;
    date_of_birth?: string;
    chronic_conditions: string[];
    allergies: string[];
  }) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profiles, setProfiles] = useState<PatientProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<PatientProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const syncActiveProfile = (list: PatientProfile[]) => {
    const savedId = getStoredProfileId();
    // Prefer Abbu in demo if no profile was explicitly selected yet, else first profile
    const chosen =
      list.find((p) => p.id === savedId) ||
      list.find((p) => p.display_name.toLowerCase().includes("abbu")) ||
      list[0] ||
      null;
    setActiveProfile(chosen);
    setStoredProfileId(chosen ? chosen.id : null);
  };

  const loadMe = async () => {
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const data = await apiFetch<{ user: AuthUser; profiles: PatientProfile[] }>("/api/auth/me");
      setUser(data.user);
      setProfiles(data.profiles);
      syncActiveProfile(data.profiles);
    } catch {
      setStoredToken(null);
      setUser(null);
      setProfiles([]);
      setActiveProfile(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMe();
  }, []);

  const applyAuth = (data: { access_token: string; user: AuthUser; profiles: PatientProfile[] }) => {
    setStoredToken(data.access_token);
    setUser(data.user);
    setProfiles(data.profiles);
    syncActiveProfile(data.profiles);
  };

  const login = async (identifier: string, password: string) => {
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
    applyAuth(data);
  };

  const demoLogin = async () => {
    const data = await apiFetch("/api/auth/demo-login", { method: "POST" });
    applyAuth(data);
  };

  const register = async (payload: {
    full_name: string;
    email?: string;
    phone_e164?: string;
    password: string;
    accepted_cloud_ai_processing: boolean;
  }) => {
    const data = await apiFetch("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    applyAuth(data);
  };

  const logout = () => {
    setStoredToken(null);
    setStoredProfileId(null);
    setUser(null);
    setProfiles([]);
    setActiveProfile(null);
  };

  const switchProfile = (profileId: string) => {
    const found = profiles.find((p) => p.id === profileId);
    if (found) {
      setActiveProfile(found);
      setStoredProfileId(found.id);
    }
  };

  const refreshProfiles = async () => {
    const data = await apiFetch<{ profiles: PatientProfile[] }>("/api/profiles");
    setProfiles(data.profiles);
    syncActiveProfile(data.profiles);
  };

  const createProfile = async (payload: {
    display_name: string;
    relationship: string;
    sex?: string;
    date_of_birth?: string;
    chronic_conditions: string[];
    allergies: string[];
  }) => {
    const res = await apiFetch<{ profile: PatientProfile }>("/api/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshProfiles();
    setStoredProfileId(res.profile.id);
    setActiveProfile(res.profile);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        profiles,
        activeProfile,
        loading,
        login,
        demoLogin,
        register,
        logout,
        switchProfile,
        refreshProfiles,
        createProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
