export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

const TOKEN_KEY = "meditrack_jwt";
const PROFILE_KEY = "meditrack_active_profile_id";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getStoredProfileId(): string | null {
  return localStorage.getItem(PROFILE_KEY);
}

export function setStoredProfileId(profileId: string | null) {
  if (profileId) localStorage.setItem(PROFILE_KEY, profileId);
  else localStorage.removeItem(PROFILE_KEY);
}

export async function apiFetch<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const profileId = getStoredProfileId();
  const headers = new Headers(init.headers || {});

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (profileId && !headers.has("X-Profile-Id")) {
    headers.set("X-Profile-Id", profileId);
  }
  if (!(init.body instanceof FormData) && !headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });
  if (res.status === 401) {
    setStoredToken(null);
    if (!window.location.pathname.startsWith("/login") && !window.location.pathname.startsWith("/brief/")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please sign in.");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  }
  return data as T;
}

export function backendUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${BACKEND_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}

export interface JobProgressEvent {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress_pct: number;
  current_step: string;
  result_id?: string;
  result_payload?: any;
  error_message?: string;
}

export function subscribeJobProgress(
  jobId: string,
  onUpdate: (ev: JobProgressEvent) => void,
  onError?: (err: string) => void
): () => void {
  const token = getStoredToken() || "";
  const profileId = getStoredProfileId() || "";
  const url = `${BACKEND_URL}/api/jobs/${jobId}/events?token=${encodeURIComponent(token)}&profile_id=${encodeURIComponent(profileId)}`;
  const es = new EventSource(url);

  es.addEventListener("progress", (e: MessageEvent) => {
    try {
      const data: JobProgressEvent = JSON.parse(e.data);
      onUpdate(data);
      if (data.status === "completed" || data.status === "failed") {
        es.close();
      }
    } catch (err) {
      console.error("SSE parse error", err);
    }
  });

  es.onerror = () => {
    es.close();
    if (onError) onError("Connection to job stream closed");
  };

  return () => es.close();
}
