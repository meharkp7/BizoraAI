import { describe, expect, it } from "vitest";
import {
  DEFAULT_VAD,
  encodeWavPcm16,
  frameRms,
  initialVadState,
  resampleMono,
  updateVad,
  type VadState,
} from "./voiceCapture.ts";

function feed(rms: number, ms: number, state: VadState = initialVadState()) {
  return updateVad(state, rms, ms, DEFAULT_VAD);
}

describe("updateVad", () => {
  it("waits through silence and brief clicks", () => {
    let state = initialVadState();
    for (let i = 0; i < 10; i += 1) {
      const step = feed(0.001, 100, state);
      state = step.state;
      expect(step.event).toBeNull();
    }
    expect(state.phase).toBe("waiting");
    // A 50ms click never trips the 120ms onset gate.
    const click = feed(0.5, 50, state);
    expect(click.event).toBeNull();
    expect(click.state.phase).toBe("waiting");
  });

  it("starts speech on sustained energy", () => {
    const step = feed(0.05, 150);
    expect(step.event).toBe("speech-start");
    expect(step.state.phase).toBe("speech");
  });

  it("ends the utterance after trailing silence", () => {
    let state = feed(0.05, 600).state;
    expect(state.phase).toBe("speech");
    // Short pauses mid-utterance do not end it.
    const pause = feed(0.001, 500, state);
    expect(pause.event).toBeNull();
    state = feed(0.05, 200, pause.state).state;
    const end = feed(0.001, DEFAULT_VAD.silenceMs, state);
    expect(end.event).toBe("utterance-end");
  });

  it("ignores silence before the minimum speech lands", () => {
    // Onset (120ms) starts the phase but 350ms of speech is required:
    // a quick burst followed by silence keeps listening.
    const started = feed(0.05, DEFAULT_VAD.onsetMs);
    expect(started.event).toBe("speech-start");
    const end = feed(0.001, DEFAULT_VAD.silenceMs, started.state);
    expect(end.event).toBeNull();
    expect(end.state.phase).toBe("speech");
  });

  it("caps the utterance at the maximum length", () => {
    const state = feed(0.05, 600).state;
    const end = updateVad(state, 0.05, DEFAULT_VAD.maxMs, DEFAULT_VAD);
    expect(end.event).toBe("utterance-end");
  });

  it("treats the threshold as inclusive", () => {
    const step = feed(DEFAULT_VAD.threshold, DEFAULT_VAD.onsetMs);
    expect(step.event).toBe("speech-start");
  });
});

describe("frameRms", () => {
  it("measures silence as zero and full scale as one", () => {
    expect(frameRms(new Float32Array(128))).toBe(0);
    expect(frameRms(Float32Array.from({ length: 64 }, () => 1))).toBeCloseTo(1);
    expect(frameRms(Float32Array.from({ length: 64 }, (_, i) => (i % 2 === 0 ? 1 : -1)))).toBeCloseTo(1);
  });
});

describe("resampleMono", () => {
  it("keeps the rate when nothing changes", () => {
    const samples = Float32Array.from([0.1, 0.2, 0.3]);
    expect(resampleMono(samples, 16000, 16000)).toEqual(samples);
  });

  it("scales length by the rate ratio", () => {
    const samples = Float32Array.from({ length: 480 }, (_, i) => i / 480);
    const down = resampleMono(samples, 48000, 16000);
    expect(down.length).toBe(160);
    expect(down[0]).toBeCloseTo(0);
    expect(down[159]).toBeLessThanOrEqual(1);
  });
});

describe("encodeWavPcm16", () => {
  it("writes a readable mono 16-bit header", () => {
    const buffer = encodeWavPcm16(new Float32Array([0, 0.5, -0.5, 1]), 16000);
    const view = new DataView(buffer);
    const ascii = (offset: number, length: number) =>
      String.fromCharCode(...new Array(length).fill(0).map((_, i) => view.getUint8(offset + i)));
    expect(buffer.byteLength).toBe(44 + 4 * 2);
    expect(ascii(0, 4)).toBe("RIFF");
    expect(ascii(8, 4)).toBe("WAVE");
    expect(ascii(12, 4)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(ascii(36, 4)).toBe("data");
    expect(view.getInt16(44, true)).toBe(0);
    expect(view.getInt16(46, true)).toBe(16384);
    expect(view.getInt16(48, true)).toBe(-16384);
    expect(view.getInt16(50, true)).toBe(32767);
  });

  it("clamps out-of-range samples instead of wrapping", () => {
    const buffer = encodeWavPcm16(new Float32Array([2, -2]), 16000);
    const view = new DataView(buffer);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});
