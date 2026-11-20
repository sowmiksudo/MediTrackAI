import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, Mic, PhoneCall, Send, Sparkles, Square } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, BACKEND_URL } from "@/lib/api";
import { AudioRecorder } from "@/utils/audio-recorder";
import { AudioStreamer } from "@/utils/audio-streamer";
import { GeminiLiveAPI, getLiveWebSocketUrl } from "@/utils/gemini-live-api";

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  citations?: string[];
  asrEngine?: string;
}

export default function CheckIn() {
  const { activeProfile } = useAuth();
  const [connected, setConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isPttPressed, setIsPttPressed] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAISpeaking, setIsAISpeaking] = useState(false);
  const [vadEngine, setVadEngine] = useState("adaptive");
  const [textInput, setTextInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pendingCitations, setPendingCitations] = useState<string[]>([]);
  const [redFlags, setRedFlags] = useState<any[]>([]);
  const [lastSummary, setLastSummary] = useState<any>(null);

  const apiRef = useRef<any>(null);
  const recorderRef = useRef<any>(null);
  const streamerRef = useRef<any>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const pendingCitationsRef = useRef<string[]>([]);

  const ensureAudioOut = async () => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 24000 });
      streamerRef.current = new AudioStreamer(audioCtxRef.current);
    }
    if (audioCtxRef.current.state === "suspended") {
      await audioCtxRef.current.resume();
    }
  };

  useEffect(() => {
    if (!activeProfile) return;
    const endpoint = getLiveWebSocketUrl(BACKEND_URL);
    const live = new GeminiLiveAPI(endpoint, true);
    apiRef.current = live;

    live.onReady = (info: any) => {
      setConnected(true);
      setVadEngine(info.vad_engine || "silero/adaptive");
    };

    live.onTranscript = (evt: any) => {
      const role = evt.role === "assistant" ? "assistant" : "user";
      const cites = role === "assistant" ? [...pendingCitationsRef.current] : [];
      if (role === "assistant") {
        pendingCitationsRef.current = [];
        setPendingCitations([]);
      }
      setTurns((prev) => [...prev, { role, text: evt.text, citations: cites, asrEngine: evt.asr_engine }]);
    };

    live.onToolEvent = (evt: any) => {
      const cites = evt.citations || [];
      pendingCitationsRef.current = [...pendingCitationsRef.current, ...cites];
      setPendingCitations([...pendingCitationsRef.current]);
    };

    live.onRedFlag = (alerts: any[]) => {
      setRedFlags(alerts);
      toast.error("Emergency Red-Flag Detected!");
    };

    live.onAudioData = async (b64: string) => {
      try {
        await ensureAudioOut();
        setIsAISpeaking(true);
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        streamerRef.current?.addPCM16(bytes);
        streamerRef.current?.resume();
      } catch (e) {
        console.error(e);
      }
    };

    live.onInterrupted = () => {
      setIsAISpeaking(false);
      streamerRef.current?.stop();
    };

    live.onTurnComplete = () => {
      setIsAISpeaking(false);
      streamerRef.current?.complete();
    };

    live.onError = (msg: string) => {
      toast.error(msg);
    };

    live.onClose = () => {
      setConnected(false);
    };

    return () => {
      recorderRef.current?.stop();
      streamerRef.current?.stop();
      audioCtxRef.current?.close().catch(() => {});
      live.close();
    };
  }, [activeProfile?.id]);

  const startMicStream = async () => {
    await ensureAudioOut();
    streamerRef.current?.stop();
    recorderRef.current = new AudioRecorder();
    await recorderRef.current.start();
    recorderRef.current.on("data", (b64: string) => {
      apiRef.current?.sendAudioChunk(b64);
    });
    setIsRecording(true);
  };

  const stopMicStream = () => {
    recorderRef.current?.stop();
    setIsRecording(false);
  };

  const handleToggleHandsFree = async () => {
    if (!connected) {
      toast.error("Voice socket connecting... try again or use text input");
      return;
    }
    try {
      if (isRecording) {
        stopMicStream();
      } else {
        await startMicStream();
        toast.success("Listening (Bangla, Banglish, or English)");
      }
    } catch (err: any) {
      toast.error(err.message || "Microphone permission needed");
    }
  };

  const handlePttDown = async () => {
    if (!connected) return;
    try {
      if (!isRecording) await startMicStream();
      setIsPttPressed(true);
      apiRef.current?.startPushToTalk();
    } catch (err: any) {
      toast.error(err.message || "Mic unavailable");
    }
  };

  const handlePttUp = () => {
    if (!isPttPressed) return;
    setIsPttPressed(false);
    apiRef.current?.endPushToTalk();
    stopMicStream();
  };

  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    const txt = textInput.trim();
    if (!txt) return;
    if (!connected) {
      toast.error("WebSocket not connected yet");
      return;
    }
    apiRef.current?.sendTextInput(txt);
    setTextInput("");
  };

  const handleFinalize = async () => {
    if (turns.length === 0) {
      toast.error("Have a short check-in conversation first before saving");
      return;
    }
    setIsSaving(true);
    try {
      const data = await apiFetch("/checkins/finalize", {
        method: "POST",
        body: JSON.stringify({
          turns: turns.map((t) => ({ role: t.role, text: t.text })),
        }),
      });
      setLastSummary(data.summary);
      if (data.red_flags?.length) setRedFlags(data.red_flags);
      toast.success("Check-in summarized & indexed into Hybrid RAG memory!");
    } catch (err: any) {
      toast.error(err.message || "Failed to save check-in");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Bilingual Voice &amp; Text Check-In</h1>
          <p className="text-sm text-muted-foreground">
            Speak naturally in <strong>Bangla</strong>, <strong>Banglish</strong>, or <strong>English</strong> for{" "}
            <strong>{activeProfile?.display_name}</strong>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={connected ? "default" : "secondary"}>
            {connected ? `Live (${vadEngine})` : "Connecting..."}
          </Badge>
          {turns.length > 0 && (
            <Button onClick={handleFinalize} disabled={isSaving} size="sm" className="gap-1.5">
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Save Check-In
            </Button>
          )}
        </div>
      </div>

      {/* Emergency Red-Flag Gate Banner */}
      {redFlags.length > 0 && (
        <Card className="border-red-500 bg-red-50 p-4 text-red-900 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              URGENT CLINICAL RED-FLAG DETECTED
            </div>
            <a href="tel:999">
              <Button size="sm" variant="destructive" className="gap-1.5">
                <PhoneCall className="h-4 w-4" /> Call BD 999
              </Button>
            </a>
          </div>
          {redFlags.map((rf, i) => (
            <div key={i} className="text-sm">
              <strong>{rf.title}:</strong> {rf.action}
            </div>
          ))}
        </Card>
      )}

      {/* Voice Controls */}
      <Card className="p-5 flex flex-col sm:flex-row items-center justify-between gap-4 bg-gradient-to-r from-primary/5 to-secondary/10">
        <div className="flex items-center gap-4">
          <Button
            onClick={handleToggleHandsFree}
            size="lg"
            variant={isRecording && !isPttPressed ? "destructive" : "default"}
            className="h-16 w-16 rounded-full shrink-0"
          >
            {isRecording && !isPttPressed ? <Square className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
          </Button>
          <div>
            <div className="font-semibold">
              {isAISpeaking
                ? "Assistant speaking..."
                : isPttPressed
                ? "Push-to-Talk active..."
                : isRecording
                ? "Hands-free listening (VAD active)"
                : "Tap Mic for Hands-Free or Hold PTT"}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Try asking: <em>&ldquo;Abbur sugar ar kidney report ki bolche?&rdquo;</em> or <em>&ldquo;Seclo ar Sergel ekshathe khawa jabe?&rdquo;</em>
            </p>
          </div>
        </div>

        {/* Hold-to-Talk Stage Noise Fallback */}
        <Button
          variant={isPttPressed ? "destructive" : "outline"}
          onMouseDown={handlePttDown}
          onMouseUp={handlePttUp}
          onMouseLeave={handlePttUp}
          onTouchStart={handlePttDown}
          onTouchEnd={handlePttUp}
          className="w-full sm:w-auto select-none"
        >
          <Mic className="h-4 w-4 mr-2" /> Hold to Talk (PTT)
        </Button>
      </Card>

      {/* Conversation Transcript + Grounded Citations */}
      <Card className="p-4 flex flex-col h-[380px]">
        <div className="flex-1 overflow-auto space-y-3 pr-1">
          {turns.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground text-sm px-4">
              <p className="font-medium text-foreground mb-1">Start your Bangla / Banglish / English check-in</p>
              <p className="text-xs max-w-md">
                Every turn runs server-side Hybrid RAG across prescriptions, normalized labs, and DGDA Bangladesh drug safety rules.
              </p>
            </div>
          ) : (
            turns.map((t, idx) => (
              <div key={idx} className={`flex flex-col ${t.role === "user" ? "items-end" : "items-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                    t.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
                  }`}
                >
                  {t.text}
                </div>
                {t.citations && t.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {t.citations.map((c, ci) => (
                      <Badge key={ci} variant="outline" className="text-[10px] bg-background">
                        {c}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
          {pendingCitations.length > 0 && (
            <div className="text-xs text-primary animate-pulse">
              Retrieving context: {pendingCitations.join(" · ")}
            </div>
          )}
        </div>

        {/* Text Fallback Bar */}
        <form onSubmit={handleSendText} className="mt-3 pt-3 border-t flex gap-2">
          <Input
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Or type in Bangla / Banglish / English..."
          />
          <Button type="submit" size="icon" disabled={!textInput.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </Card>

      {lastSummary && (
        <Card className="p-4 border-emerald-200 bg-emerald-50/50 space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-emerald-900">Saved Check-In Summary</span>
            <Badge className="capitalize">{lastSummary.overall_score}</Badge>
          </div>
          <p className="text-slate-700">{lastSummary.summary}</p>
        </Card>
      )}
    </div>
  );
}
