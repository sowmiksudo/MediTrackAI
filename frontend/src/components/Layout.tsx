import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Cpu, LogOut, Plus, Users } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sidebar } from "./Sidebar";
import { TelemetryDrawer } from "./TelemetryDrawer";
import { useAuth } from "@/context/AuthContext";
import { apiFetch } from "@/lib/api";

export const Layout = () => {
  const { profiles, activeProfile, switchProfile, logout, createProfile } = useAuth();
  const [telemetryOpen, setTelemetryOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [modeLabel, setModeLabel] = useState<string>("cloud");

  const [newName, setNewName] = useState("");
  const [newRel, setNewRel] = useState("parent");
  const [newSex, setNewSex] = useState("M");
  const [newDob, setNewDob] = useState("");
  const [newCond, setNewCond] = useState("");

  useEffect(() => {
    apiFetch("/api/telemetry/status")
      .then((d) => setModeLabel(d?.runtime?.inference_mode || "cloud"))
      .catch(() => {});
  }, []);

  const handleAddProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createProfile({
        display_name: newName,
        relationship: newRel,
        sex: newSex,
        date_of_birth: newDob || undefined,
        chronic_conditions: newCond
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        allergies: [],
      });
      toast.success(`Profile '${newName}' added`);
      setAddOpen(false);
      setNewName("");
      setNewCond("");
    } catch (err: any) {
      toast.error(err.message || "Failed to add profile");
    }
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        {/* Global Top Header with Family Switcher & Telemetry Drawer Trigger */}
        <header className="flex items-center justify-between gap-2 border-b border-border bg-card px-4 py-2.5 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Users className="h-4 w-4 text-primary shrink-0" />
            <Select
              value={activeProfile?.id || ""}
              onValueChange={(val) => {
                if (val === "__new__") setAddOpen(true);
                else switchProfile(val);
              }}
            >
              <SelectTrigger className="h-8 w-[190px] sm:w-[240px] text-xs font-medium">
                <SelectValue placeholder="Select patient profile" />
              </SelectTrigger>
              <SelectContent>
                {profiles.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.display_name} ({p.relationship})
                  </SelectItem>
                ))}
                <SelectItem value="__new__" className="text-primary font-medium">
                  + Add Family Member
                </SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" size="icon" className="h-8 w-8 hidden sm:inline-flex" onClick={() => setAddOpen(true)} title="Add Family Profile">
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={modeLabel === "hybrid_gpu" ? "default" : "secondary"} className="hidden sm:inline-flex text-[11px]">
              {modeLabel === "hybrid_gpu" ? "Hybrid GPU" : "Cloud API"}
            </Badge>
            <Button variant="outline" size="sm" className="h-8 text-xs gap-1.5" onClick={() => setTelemetryOpen(true)}>
              <Cpu className="h-3.5 w-3.5 text-primary" />
              <span className="hidden sm:inline">AI Telemetry</span>
              <span className="sm:hidden">RAG</span>
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={logout} title="Sign Out">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <main className="flex-1 overflow-auto pb-16 md:pb-0">
          <Outlet key={activeProfile?.id || "none"} />
        </main>
      </div>

      <TelemetryDrawer open={telemetryOpen} onClose={() => setTelemetryOpen(false)} />

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Family Patient Profile</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddProfile} className="space-y-3">
            <div className="space-y-1">
              <Label>Name / Label</Label>
              <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g., Dada, Nana, Uncle" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Relationship</Label>
                <Select value={newRel} onValueChange={setNewRel}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="parent">Parent</SelectItem>
                    <SelectItem value="spouse">Spouse</SelectItem>
                    <SelectItem value="child">Child</SelectItem>
                    <SelectItem value="self">Self</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Sex (for eGFR / Labs)</Label>
                <Select value={newSex} onValueChange={setNewSex}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="M">Male</SelectItem>
                    <SelectItem value="F">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Date of Birth</Label>
              <Input type="date" value={newDob} onChange={(e) => setNewDob(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Chronic Conditions (comma separated)</Label>
              <Input value={newCond} onChange={(e) => setNewCond(e.target.value)} placeholder="Type 2 Diabetes, Hypertension" />
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
              <Button type="submit">Save Profile</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};
