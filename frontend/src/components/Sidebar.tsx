import { NavLink } from "react-router-dom";
import { Activity, FileText, MessageSquare, Stethoscope, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
  { name: "Check-In", href: "/", icon: MessageSquare },
  { name: "Upload", href: "/upload", icon: Upload },
  { name: "Records", href: "/summaries", icon: FileText },
  { name: "Visit Prep", href: "/visit-prep", icon: Stethoscope },
];

export const Sidebar = () => {
  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex h-screen w-60 flex-col border-r border-border bg-card shrink-0">
        <div className="flex h-16 items-center gap-3 border-b border-border px-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-foreground leading-tight">MediTrackAI</h1>
            <p className="text-[11px] text-muted-foreground">Bangladesh Care Vault</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              end={item.href === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border p-4 space-y-2.5">
          <NavLink
            to="/docs"
            className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-xs font-semibold text-foreground hover:border-primary/40 hover:bg-primary/5 transition-colors"
          >
            <span>Live Pitch & Docs</span>
            <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] text-primary">/docs</span>
          </NavLink>
          <div className="rounded-lg bg-primary/5 border border-primary/15 p-3">
            <p className="text-xs font-semibold text-primary">BD Clinical Companion</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Bangla voice · DGDA drug checks · 1-page doctor brief
            </p>
          </div>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-card/95 backdrop-blur flex justify-around py-1.5 px-1">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            end={item.href === "/"}
            className={({ isActive }) =>
              cn(
                "flex flex-col items-center gap-0.5 rounded-md px-3 py-1.5 text-[11px] font-medium",
                isActive ? "text-primary" : "text-muted-foreground"
              )
            }
          >
            <item.icon className="h-5 w-5" />
            <span>{item.name}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
};
