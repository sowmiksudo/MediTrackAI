import { useState } from "react";
import { Mail, Users } from "lucide-react";

export interface TeamMember {
  id: number;
  full_name: string;
  role_title: string;
  email: string;
  avatar_url?: string;
  sort_order: number;
  is_active: boolean;
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0]?.toUpperCase() || "")
    .join("");
}

function AvatarFrame({ name, url }: { name: string; url?: string }) {
  const [broken, setBroken] = useState(false);
  const showImg = Boolean(url && url.trim() && !broken);

  return (
    <div className="mx-auto h-24 w-24 aspect-square rounded-2xl border-2 border-primary/20 bg-primary/10 overflow-hidden flex items-center justify-center shadow-sm">
      {showImg ? (
        <img
          src={url}
          alt={name}
          onError={() => setBroken(true)}
          className="h-full w-full object-cover object-center"
        />
      ) : (
        <span className="text-xl font-bold tracking-wide text-primary">{getInitials(name)}</span>
      )}
    </div>
  );
}

export function TeamGrid({ teamName, members }: { teamName: string; members: TeamMember[] }) {
  if (!members.length) return null;

  return (
    <div className="mt-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Users className="h-4 w-4 text-primary" />
        <span>{teamName || "Team MediTrackAI"}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {members.map((m) => (
          <div
            key={m.id}
            className="flex flex-col items-center text-center rounded-xl border border-border bg-card p-4 shadow-sm hover:border-primary/40 transition-colors"
          >
            <AvatarFrame name={m.full_name} url={m.avatar_url} />
            <h4 className="mt-3 text-sm font-bold text-foreground leading-snug">{m.full_name}</h4>
            <p className="mt-1 text-xs font-medium text-primary leading-snug">{m.role_title}</p>
            <a
              href={`mailto:${m.email}`}
              className="mt-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground break-all"
            >
              <Mail className="h-3 w-3 shrink-0" />
              <span>{m.email}</span>
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
