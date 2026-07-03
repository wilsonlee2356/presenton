import { SrtEntry } from "@/app/(presentation-generator)/services/api/chatterbox-types";

/**
 * Run an async function over `items` with at most `concurrency` calls in flight.
 */
export async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let index = 0;

  const worker = async () => {
    while (index < items.length) {
      const i = index++;
      results[i] = await fn(items[i], i);
    }
  };

  await Promise.all(Array.from({ length: concurrency }, worker));
  return results;
}

/**
 * Convert an SRT timestamp (HH:MM:SS,mmm) to milliseconds.
 */
function parseSrtTime(time: string): number {
  const cleaned = time.trim().replace(".", ",");
  const match = cleaned.match(/^(\d{2}):(\d{2}):(\d{2}),(\d{3})$/);
  if (!match) {
    throw new Error(`Invalid SRT time format: ${time}`);
  }
  const [, hours, minutes, seconds, millis] = match;
  return (
    parseInt(hours, 10) * 3600000 +
    parseInt(minutes, 10) * 60000 +
    parseInt(seconds, 10) * 1000 +
    parseInt(millis, 10)
  );
}

/**
 * Remove simple HTML-like tags from subtitle text so they are not spoken.
 */
function stripTags(text: string): string {
  return text.replace(/<[^>]+>/g, "").trim();
}

/**
 * Format milliseconds as HH:MM:SS.mmm for display.
 */
export function formatSrtTime(ms: number): string {
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const millis = Math.floor(ms % 1000);
  const pad = (n: number, len = 2) => String(n).padStart(len, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}.${pad(millis, 3)}`;
}

/**
 * Parse SubRip (.srt) file contents into timed entries.
 * Malformed blocks are skipped and returned via the `skipped` array.
 */
export function parseSrt(content: string): {
  entries: SrtEntry[];
  skipped: number;
} {
  const blocks = content.replace(/\r\n/g, "\n").split(/\n\s*\n/);
  const entries: SrtEntry[] = [];
  let skipped = 0;

  for (const block of blocks) {
    const lines = block.trim().split("\n").filter(Boolean);
    if (lines.length < 2) {
      if (block.trim()) skipped += 1;
      continue;
    }

    const indexLine = lines[0].trim();
    const timeLine = lines[1].trim();
    const text = lines.slice(2).join("\n").trim();

    const index = parseInt(indexLine, 10);
    if (Number.isNaN(index)) {
      skipped += 1;
      continue;
    }

    const timeMatch = timeLine.match(
      /^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})$/
    );
    if (!timeMatch) {
      skipped += 1;
      continue;
    }

    try {
      const startMs = parseSrtTime(timeMatch[1]);
      const endMs = parseSrtTime(timeMatch[2]);
      if (endMs <= startMs) {
        skipped += 1;
        continue;
      }
      const cleanText = stripTags(text);
      if (!cleanText) {
        skipped += 1;
        continue;
      }
      entries.push({ index, startMs, endMs, text: cleanText });
    } catch {
      skipped += 1;
    }
  }

  return { entries, skipped };
}

/**
 * Decode a list of audio blobs into AudioBuffers.
 * `null` blobs are returned as `null` so callers can keep array alignment.
 */
async function decodeBlobs(
  blobs: (Blob | null)[]
): Promise<(AudioBuffer | null)[]> {
  const ctx = new AudioContext();
  const buffers: (AudioBuffer | null)[] = [];

  for (const blob of blobs) {
    if (!blob) {
      buffers.push(null);
      continue;
    }
    try {
      const arrayBuffer = await blob.arrayBuffer();
      const decoded = await ctx.decodeAudioData(arrayBuffer);
      buffers.push(decoded);
    } catch {
      buffers.push(null);
    }
  }

  await ctx.close();
  return buffers;
}

/**
 * Mix generated TTS clips onto a timeline defined by SRT entries.
 * Each clip starts at its entry's startMs and runs until it naturally ends.
 * The final output is a WAV Blob.
 */
export async function mixSrtAudio(
  blobs: (Blob | null)[],
  entries: SrtEntry[],
  sampleRate = 44100
): Promise<Blob> {
  if (blobs.length !== entries.length) {
    throw new Error("Mismatched blobs and entries counts");
  }

  const buffers = await decodeBlobs(blobs);
  const maxEndMs = entries.length > 0 ? entries[entries.length - 1].endMs : 0;
  const paddingSeconds = 1;
  const durationSeconds = maxEndMs / 1000 + paddingSeconds;

  const offline = new OfflineAudioContext(
    2,
    Math.ceil(sampleRate * durationSeconds),
    sampleRate
  );

  entries.forEach((entry, i) => {
    const buffer = buffers[i];
    if (!buffer) return;

    const source = offline.createBufferSource();
    source.buffer = buffer;
    source.connect(offline.destination);
    source.start(entry.startMs / 1000);
  });

  const rendered = await offline.startRendering();
  return audioBufferToWav(rendered);
}

/**
 * Encode an AudioBuffer as a PCM WAV Blob.
 */
export function audioBufferToWav(buffer: AudioBuffer): Blob {
  const numOfChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;
  const bytesPerSample = bitDepth / 8;
  const blockAlign = numOfChannels * bytesPerSample;

  const interleaved = interleaveBuffer(buffer);
  const dataLength = interleaved.length * bytesPerSample;
  const bufferLength = 44 + dataLength;
  const arrayBuffer = new ArrayBuffer(bufferLength);
  const view = new DataView(arrayBuffer);

  const writeString = (offset: number, string: string) => {
    for (let i = 0; i < string.length; i += 1) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, format, true);
  view.setUint16(22, numOfChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(36, "data");
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < interleaved.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, interleaved[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Blob([arrayBuffer], { type: "audio/wav" });
}

function interleaveBuffer(buffer: AudioBuffer): Float32Array {
  if (buffer.numberOfChannels === 1) {
    return buffer.getChannelData(0);
  }

  const channels: Float32Array[] = [];
  for (let i = 0; i < buffer.numberOfChannels; i += 1) {
    channels.push(buffer.getChannelData(i));
  }

  const length = buffer.length;
  const interleaved = new Float32Array(length * buffer.numberOfChannels);
  for (let i = 0; i < length; i += 1) {
    for (let c = 0; c < buffer.numberOfChannels; c += 1) {
      interleaved[i * buffer.numberOfChannels + c] = channels[c][i];
    }
  }
  return interleaved;
}
