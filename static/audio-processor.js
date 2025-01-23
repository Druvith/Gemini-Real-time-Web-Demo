class Resample16kWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.inputSampleRate = options.processorOptions.inputSampleRate || 48000;
    this.outputSampleRate = 16000;
    this.resampleRatio = this.inputSampleRate / this.outputSampleRate;
    this._buffer = new Int16Array(512);
    this._bufferIndex = 0;
  }

  _resampleBlock(input) {
    const outBlock = [];
    let idxInput = 0.0;
    while (idxInput < input.length) {
      const low = Math.floor(idxInput);
      const high = Math.min(low + 1, input.length - 1);
      const frac = idxInput - low;
      const sampleF = (1 - frac) * input[low] + frac * input[high];
      const s = Math.max(-1, Math.min(1, sampleF));
      outBlock.push(s < 0 ? s * 0x8000 : s * 0x7FFF);
      idxInput += this.resampleRatio;
    }
    return new Int16Array(outBlock);
  }

  process(inputs, outputs) {
    if (!inputs[0] || !inputs[0][0] || inputs[0][0].length === 0) return true;
    
    const inputFloat = inputs[0][0];
    const block16 = this._resampleBlock(inputFloat);

    let iBlock = 0;
    while (iBlock < block16.length) {
      this._buffer[this._bufferIndex++] = block16[iBlock++];
      if (this._bufferIndex === 512) {
        this.port.postMessage(this._buffer.buffer, [this._buffer.buffer]);
        this._buffer = new Int16Array(512);
        this._bufferIndex = 0;
      }
    }
    return true;
  }
}

registerProcessor("resample-16k-worklet", Resample16kWorklet);
