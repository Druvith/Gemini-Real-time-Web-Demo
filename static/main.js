let audioContext = null;
let mediaStream = null;
let workletNode = null;
let ws = null;
let isRecording = false;
let audioQueue = [];
let isPlaying = false;
let nextPlaybackTime = 0;
const SCHEDULE_AHEAD_TIME = 0.1; // Schedule 100ms ahead
let playbackNode = null;
let isMuted = false;
let isPTTPressed = false;

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const sendTextBtn = document.getElementById("sendTextBtn");
const textInput = document.getElementById("textInput");
const statusDiv = document.getElementById("status");
const logDiv = document.getElementById("log");
const volumeSlider = document.getElementById("volumeSlider");
const volumeLabel = document.getElementById("volumeLabel");
const muteBtn = document.getElementById("muteBtn");

startBtn.addEventListener("click", startRecording);
stopBtn.addEventListener("click", stopRecording);
sendTextBtn.addEventListener("click", sendText);
muteBtn.addEventListener("click", toggleMute);
volumeSlider.addEventListener("input", updateVolume);
window.addEventListener("keydown", handleKeyDown);
window.addEventListener("keyup", handleKeyUp);

function logMessage(...msg) {
  console.log("[Client]", ...msg);
  logDiv.innerHTML += `<div>${msg.join(" ")}</div>`;
  logDiv.scrollTop = logDiv.scrollHeight;
}

// WebSocket setup
function initWebSocket() {
  if (ws) return;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/ws`;
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    statusDiv.textContent = "Status: Connected";
    logMessage("WebSocket connected.");
    ws.send("ACK:CLIENT_READY");
  };

  ws.onmessage = handleWebSocketMessage;
  ws.onerror = err => logMessage("WebSocket error:", err);
  ws.onclose = () => {
    statusDiv.textContent = "Status: Disconnected";
    logMessage("WebSocket closed.");
    logMessage("[Server] Gemini session closed. WebSocket endpoint done.");
    ws = null;
  };
}

// Message handling
async function handleWebSocketMessage(event) {
  if (typeof event.data === "string") {
    handleTextMessage(event.data);
  } else {
    handleAudioMessage(event.data);
  }
}

function handleTextMessage(text) {
  if (text.startsWith("ACK:")) {
    logMessage("Server ACK:", text);
  } else if (text.startsWith("TEXT:")) {
    logMessage("Gemini:", text.slice(5));
  }
}

function handleAudioMessage(data) {
  const dataArr = new Uint8Array(data);
  if (new TextDecoder().decode(dataArr.slice(0,6)) === "AUDIO:") {
    const audioData = dataArr.slice(6);
    if (playbackNode) {
      playbackNode.port.postMessage({
        type: "AUDIO_DATA",
        data: audioData
      });
      logMessage("Sent audio chunk to playback processor:", audioData.byteLength, "bytes");
    }
  }
}

// Audio handling
async function startRecording() {
  try {
    await setupAudioContext();
    await setupMicrophone();
    initWebSocket();
    updateUIForRecording(true);
    if (isPTTPressed) {
      logMessage("Push-to-talk active");
    }
  } catch (e) {
    logMessage("Start recording error:", e);
  }
}

async function setupAudioContext() {
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000  // Request 24kHz sample rate
      });
      logMessage("AudioContext created at", audioContext.sampleRate, "Hz");
      
      try {
        await audioContext.audioWorklet.addModule("/static/audio-processor.js");
        await audioContext.audioWorklet.addModule("/static/playback-processor.js");
        logMessage("AudioWorklets loaded successfully");

        // Create and configure playback node
        playbackNode = new AudioWorkletNode(audioContext, "playback-processor");
        playbackNode.port.onmessage = (evt) => {
          const msg = evt.data;
          if (msg.type === "BUFFER_STATS") {
            logMessage(`Buffer ~${msg.msBuffered}ms, isBuffering=${msg.isBuffering}`);
          } else if (msg.type === "STATE_CHANGE") {
            logMessage(`Playback state: ${msg.event}, buffered=${msg.bufferedSamples}`);
          }
        };
        
        playbackNode.connect(audioContext.destination);
        logMessage("Playback node connected");
      } catch (workletError) {
        logMessage("Failed to load AudioWorklets:", workletError);
        throw workletError;
      }
    }
    
    if (audioContext.state === "suspended") {
      await audioContext.resume();
      logMessage("AudioContext resumed");
    }
  } catch (error) {
    logMessage("AudioContext setup error:", error);
    throw error;
  }
}

async function setupMicrophone() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
    logMessage("Microphone access granted");

    workletNode = new AudioWorkletNode(audioContext, "resample-16k-worklet", {
      processorOptions: { inputSampleRate: audioContext.sampleRate }
    });
    
    workletNode.port.onmessage = evt => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(evt.data);
        logMessage("Sent audio chunk:", evt.data.byteLength, "bytes");
      }
    };

    workletNode.onprocessorerror = error => {
      logMessage("AudioWorklet processing error:", error);
    };

    const source = audioContext.createMediaStreamSource(mediaStream);
    source.connect(workletNode);
    logMessage("Audio processing pipeline connected");
  } catch (error) {
    logMessage("Microphone setup error:", error);
    throw error;
  }
}

function stopRecording() {
  mediaStream?.getTracks().forEach(track => track.stop());
  workletNode?.disconnect();
  mediaStream = null;
  workletNode = null;
  audioQueue = []; // Clear any pending audio
  isPlaying = false;
  nextPlaybackTime = 0; // Reset playback timing
  if (playbackNode) {
    playbackNode.disconnect();
    playbackNode = null;
  }
  updateUIForRecording(false);
  if (isPTTPressed) {
    logMessage("Push-to-talk released");
  }
}

function updateUIForRecording(isRecording) {
  startBtn.disabled = isRecording;
  stopBtn.disabled = !isRecording;
  startBtn.classList.toggle('recording', isRecording);
  logMessage(isRecording ? "Recording started" : "Recording stopped");
}

function sendText() {
  const text = textInput.value.trim();
  if (text && ws?.readyState === WebSocket.OPEN) {
    ws.send("TEXT:" + text);
    logMessage("You:", text);
    textInput.value = "";
  }
}

function toggleMute() {
  isMuted = !isMuted;
  muteBtn.textContent = isMuted ? "🔇" : "🔊";
  if (playbackNode) {
    playbackNode.port.postMessage({ type: "SET_MUTE", value: isMuted });
  }
}

function updateVolume() {
  const volume = volumeSlider.value / 100;
  volumeLabel.textContent = `${volumeSlider.value}%`;
  if (playbackNode) {
    playbackNode.port.postMessage({ 
      type: "SET_VOLUME", 
      value: volume 
    });
    logMessage("Volume updated:", `${volumeSlider.value}%`);
  }
}

function handleKeyDown(event) {
  // Space key handling
  if ((event.code === "Space" || event.key === " ") && !event.repeat) {
    // Only prevent default and handle PTT if not typing in text input
    if (document.activeElement !== textInput) {
      event.preventDefault();
      if (!isPTTPressed && !isRecording) {
        isPTTPressed = true;
        startBtn.classList.add('active');
        startRecording();
      }
    }
  } 
  // Enter key handling
  else if ((event.code === "Enter" || event.key === "Enter") && !event.repeat && document.activeElement === textInput) {
    event.preventDefault();
    sendText();
  } 
  // Escape key handling
  else if (event.code === "Escape" || event.key === "Escape") {
    if (isRecording) {
      stopBtn.click();
    }
  }
}

function handleKeyUp(event) {
  if ((event.code === "Space" || event.key === " ") && isPTTPressed) {
    event.preventDefault();
    isPTTPressed = false;
    startBtn.classList.remove('active'); // Visual feedback
    if (isRecording) {
      stopRecording();
    }
  }
}
