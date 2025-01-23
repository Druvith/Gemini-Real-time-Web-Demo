class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Tunable parameters
    this.sampleRate = 24000;
    this.ringBufferLength = this.sampleRate * 5; // 5 seconds buffer
    this.initialBufferMs = 300;
    this.initialBufferSize = Math.floor(this.sampleRate * (this.initialBufferMs / 1000));
    this.rebufferMs = 150;
    this.rebufferThreshold = Math.floor(this.sampleRate * (this.rebufferMs / 1000));

    // Ring buffer storage
    this.ringBuffer = new Float32Array(this.ringBufferLength);
    this.writeIndex = 0;
    this.readIndex = 0;
    this.bufferedSamples = 0;

    // Playback state
    this.isBuffering = true;
    this.lastReportTime = 0;

    this.port.onmessage = (event) => {
      const { type, data } = event.data || {};
      if (type === "AUDIO_DATA" && data instanceof Uint8Array) {
        this._handleIncomingPCM(data);
      }
    };
  }

  _handleIncomingPCM(uint8) {
    const int16View = new Int16Array(uint8.buffer, uint8.byteOffset, uint8.byteLength / 2);

    for (let i = 0; i < int16View.length; i++) {
      const sampleFloat = Math.max(-1, Math.min(1, int16View[i] / 32767));
      this.ringBuffer[this.writeIndex] = sampleFloat;
      this.writeIndex = (this.writeIndex + 1) % this.ringBufferLength;

      if (this.writeIndex === this.readIndex) {
        this.readIndex = (this.readIndex + 1) % this.ringBufferLength;
      } else {
        this.bufferedSamples++;
        if (this.bufferedSamples > this.ringBufferLength) {
          this.bufferedSamples = this.ringBufferLength;
        }
      }
    }

    if (this.isBuffering && this.bufferedSamples >= this.initialBufferSize) {
      this.isBuffering = false;
      this._postStateChange("PLAYING_START");
    }
  }

  _readFromRingBuffer(output, frames) {
    if (this.isBuffering) {
      output.fill(0);
      return;
    }

    for (let i = 0; i < frames; i++) {
      if (this.bufferedSamples > 0) {
        output[i] = this.ringBuffer[this.readIndex];
        this.readIndex = (this.readIndex + 1) % this.ringBufferLength;
        this.bufferedSamples--;
      } else {
        output[i] = 0;
      }
    }

    if (!this.isBuffering && this.bufferedSamples < this.rebufferThreshold) {
      this.isBuffering = true;
      this._postStateChange("BUFFERING_RESTART");
    }
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    if (!output || output.length < 1) return true;

    const channelData = output[0];
    this._readFromRingBuffer(channelData, channelData.length);

    const now = currentTime;
    if (now - this.lastReportTime >= 0.5) {
      this.lastReportTime = now;
      const msBuffered = (this.bufferedSamples / this.sampleRate) * 1000;
      this.port.postMessage({
        type: "BUFFER_STATS",
        isBuffering: this.isBuffering,
        bufferedSamples: this.bufferedSamples,
        msBuffered: Math.floor(msBuffered),
      });
    }

    return true;
  }

  _postStateChange(eventLabel) {
    this.port.postMessage({
      type: "STATE_CHANGE",
      event: eventLabel,
      bufferedSamples: this.bufferedSamples,
    });
  }
}

registerProcessor("playback-processor", PlaybackProcessor);
