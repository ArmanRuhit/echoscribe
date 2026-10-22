class PCMWorklet extends AudioWorkletProcessor {
    constructor() {
        super();
        this.chunk = new Int16Array(1600);
        this.offset = 0;
    }

    process(inputs) {
        const channels = inputs[0];
        if (!channels?.length) return true;

        const frames = channels[0].length;
        for (let i = 0; i < frames; i += 1) {
            let mixed = 0;
            for (let c = 0; c < channels.length; c += 1) {
                mixed += channels[c][i];
            }
            const sample = Math.max(-1, Math.min(1, mixed / channels.length));
            this.chunk[this.offset] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
            this.offset += 1;

            if (this.offset === this.chunk.length) {
                this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
                this.chunk = new Int16Array(1600);
                this.offset = 0;
            }
        }

        return true;
    }
}

registerProcessor("pcm-worklet", PCMWorklet);