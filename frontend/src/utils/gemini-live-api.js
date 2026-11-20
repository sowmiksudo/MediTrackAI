import { getStoredProfileId, getStoredToken } from "@/lib/api";

export function getLiveWebSocketUrl(backendUrl = "http://localhost:8000") {
  const token = encodeURIComponent(getStoredToken() || "");
  const profileId = encodeURIComponent(getStoredProfileId() || "");
  const query = `?token=${token}&profile_id=${profileId}`;
  if (backendUrl.startsWith("/")) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}${backendUrl}/ws/live${query}`;
  }
  return `${backendUrl.replace(/^http/, "ws").replace(/\/$/, "")}/ws/live${query}`;
}

export class GeminiLiveAPI {
  constructor(endpoint, autoSetup = true, setupConfig = null) {
    this.ws = new WebSocket(endpoint);
    this.onSetupComplete = () => {};
    this.onReady = () => {};
    this.onAudioData = () => {};
    this.onTranscript = () => {};
    this.onToolEvent = () => {};
    this.onRedFlag = () => {};
    this.onPiiDiff = () => {};
    this.onInterrupted = () => {};
    this.onTurnComplete = () => {};
    this.onError = () => {};
    this.onClose = () => {};
    this.pendingSetupMessage = null;
    this.autoSetup = autoSetup;
    this.setupConfig = setupConfig;

    this.setupWebSocket();
  }

  setupWebSocket() {
    this.ws.onopen = () => {
      if (this.autoSetup) {
        this.sendDefaultSetup();
      } else if (this.pendingSetupMessage) {
        this.ws.send(JSON.stringify(this.pendingSetupMessage));
        this.pendingSetupMessage = null;
      }
    };

    this.ws.onmessage = async (event) => {
      try {
        let wsResponse;
        if (event.data instanceof Blob) {
          wsResponse = JSON.parse(await event.data.text());
        } else {
          wsResponse = JSON.parse(event.data);
        }

        if (wsResponse.setupComplete) {
          this.onSetupComplete();
        } else if (wsResponse.type === "ready") {
          this.onReady(wsResponse);
        } else if (wsResponse.type === "transcript") {
          this.onTranscript(wsResponse);
        } else if (wsResponse.type === "tool_event") {
          this.onToolEvent(wsResponse);
        } else if (wsResponse.type === "red_flag") {
          this.onRedFlag(wsResponse.alerts || []);
        } else if (wsResponse.type === "pii_diff") {
          this.onPiiDiff(wsResponse);
        } else if (wsResponse.type === "error") {
          this.onError(wsResponse.detail || "Voice pipeline error");
        } else if (wsResponse.serverContent) {
          if (wsResponse.serverContent.interrupted) {
            this.onInterrupted();
            return;
          }
          const parts = wsResponse.serverContent.modelTurn?.parts || [];
          for (const part of parts) {
            if (part?.inlineData?.data) {
              this.onAudioData(part.inlineData.data);
            }
          }
          if (wsResponse.serverContent.turnComplete) {
            this.onTurnComplete();
          }
        }
      } catch (error) {
        console.error("Error parsing WS response:", error);
      }
    };

    this.ws.onerror = () => {
      this.onError("WebSocket connection error");
    };

    this.ws.onclose = (event) => {
      this.onClose(event);
    };
  }

  sendMessage(message) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  sendSetupMessage(setupMessage) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(setupMessage));
    } else {
      this.pendingSetupMessage = setupMessage;
    }
  }

  sendDefaultSetup() {
    const setupMessage = {
      setup: this.setupConfig || {
        generation_config: {
          response_modalities: ["audio"],
          speech_config: { voice_config: { prebuilt_voice_config: { voice_name: "Aoede" } } },
        },
      },
    };
    this.sendSetupMessage(setupMessage);
  }

  sendAudioChunk(base64Audio) {
    this.sendMessage({
      realtime_input: {
        media_chunks: [{ mime_type: "audio/pcm", data: base64Audio }],
      },
    });
  }

  startPushToTalk() {
    this.sendMessage({ type: "ptt_start" });
  }

  endPushToTalk() {
    this.sendMessage({ type: "ptt_end" });
  }

  sendTextInput(text) {
    this.sendMessage({ type: "text_input", text });
  }

  close() {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) {
      this.ws.close();
    }
  }
}
