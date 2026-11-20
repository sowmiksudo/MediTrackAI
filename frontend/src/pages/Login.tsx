import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, Lock, ShieldCheck, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const { login, demoLogin, register } = useAuth();
  const [busy, setBusy] = useState(false);

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");

  const [fullName, setFullName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPhone, setRegPhone] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [pdpaAccepted, setPdpaAccepted] = useState(true);

  const handleDemo = async () => {
    setBusy(true);
    try {
      await demoLogin();
      toast.success("Loaded Dhaka Family Vault (Sadia, Abbu & Ammu)");
      navigate("/");
    } catch (err: any) {
      toast.error(err.message || "Demo login failed");
    } finally {
      setBusy(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(identifier, password);
      toast.success("Welcome back to MediTrackAI");
      navigate("/");
    } catch (err: any) {
      toast.error(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pdpaAccepted) {
      toast.error("Please accept the PDPA 2026 consent notice to continue");
      return;
    }
    setBusy(true);
    try {
      await register({
        full_name: fullName,
        email: regEmail || undefined,
        phone_e164: regPhone || undefined,
        password: regPassword,
        accepted_cloud_ai_processing: pdpaAccepted,
      });
      toast.success("Family vault created!");
      navigate("/");
    } catch (err: any) {
      toast.error(err.message || "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-teal-50 p-4">
      <div className="w-full max-w-md space-y-5">
        <div className="text-center space-y-2">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-md">
            <Activity className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">MediTrackAI Bangladesh</h1>
          <p className="text-sm text-slate-600">
            Bilingual Bangla Voice · Handwritten Rx &amp; Lab Vault · 1-Page Doctor Brief
          </p>
        </div>

        {/* 1-Click Demo Login Banner */}
        <Card className="border-primary/30 bg-primary/5 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <Users className="h-5 w-5 text-primary mt-0.5 shrink-0" />
            <div className="text-xs text-slate-700 space-y-1">
              <p className="font-semibold text-slate-900 text-sm">Hackathon / Evaluator Quick-Start</p>
              <p>
                Instantly load <strong>Abbu (62M · Diabetes + HTN)</strong> with 3 normalized{" "}
                <code>mmol/L</code> labs, live <strong>Seclo + Sergel Duplicate PPI alert</strong>, and Banglish check-ins.
              </p>
            </div>
          </div>
          <Button onClick={handleDemo} disabled={busy} className="w-full gap-2" size="lg">
            <Sparkles className="h-4 w-4" />
            {busy ? "Signing in..." : "Demo Login (Dhaka Family)"}
          </Button>
        </Card>

        <Card className="p-6 shadow-sm">
          <Tabs defaultValue="login">
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="login">Sign In</TabsTrigger>
              <TabsTrigger value="register">Create Vault</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Email or Phone (+880...)</Label>
                  <Input
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    placeholder="demo@meditrack.bd or +88017..."
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Password</Label>
                  <Input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                  />
                </div>
                <Button type="submit" disabled={busy} variant="outline" className="w-full">
                  <Lock className="mr-2 h-4 w-4" /> Sign In
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={handleRegister} className="space-y-3">
                <div className="space-y-1">
                  <Label>Full Name</Label>
                  <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Sadia Rahman" required />
                </div>
                <div className="space-y-1">
                  <Label>Email (optional if phone given)</Label>
                  <Input type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} placeholder="sadia@example.com" />
                </div>
                <div className="space-y-1">
                  <Label>Bangladesh Phone (optional)</Label>
                  <Input value={regPhone} onChange={(e) => setRegPhone(e.target.value)} placeholder="+8801711000000" />
                </div>
                <div className="space-y-1">
                  <Label>Password (min 6 chars)</Label>
                  <Input type="password" value={regPassword} onChange={(e) => setRegPassword(e.target.value)} minLength={6} required />
                </div>
                <div className="flex items-start gap-2 rounded-md bg-slate-50 p-2.5 text-xs text-slate-600 border">
                  <Checkbox id="pdpa" checked={pdpaAccepted} onCheckedChange={(v) => setPdpaAccepted(Boolean(v))} />
                  <label htmlFor="pdpa" className="leading-snug cursor-pointer">
                    <strong>PDPA 2026 Consent:</strong> I consent to encrypted storage and PII-masked AI clinical summarization for my family profiles.
                  </label>
                </div>
                <Button type="submit" disabled={busy} className="w-full">
                  Create Account
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </Card>

        <div className="flex items-center justify-center gap-2 text-xs text-slate-500">
          <ShieldCheck className="h-4 w-4 text-emerald-600" />
          <span>Profile-Scoped JWT Auth · Non-Diagnostic Clinical Companion</span>
        </div>
      </div>
    </div>
  );
}
