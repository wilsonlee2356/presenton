/**
 * TypeScript types derived from the Chatterbox TTS Server OpenAPI spec.
 * These map to the request/response schemas exposed by the standalone TTS service.
 */

export type VoiceMode = "predefined" | "clone";
export type OutputFormat = "wav" | "opus" | "mp3";
export type OpenAIResponseFormat = "wav" | "opus" | "mp3";

export interface CustomTTSRequest {
  /** Text to be synthesized. */
  text: string;
  /** Voice mode: 'predefined' for a built-in voice, 'clone' for voice cloning using a reference audio. */
  voice_mode?: VoiceMode;
  /** Filename of the predefined voice to use (e.g., 'default_sample.wav'). Required if voice_mode is 'predefined'. */
  predefined_voice_id?: string | null;
  /** Filename of a user-uploaded reference audio for voice cloning. Required if voice_mode is 'clone'. */
  reference_audio_filename?: string | null;
  /** Desired audio output format. */
  output_format?: OutputFormat;
  /** Whether to automatically split long text into chunks for processing. */
  split_text?: boolean | null;
  /** Approximate target character length for text chunks when splitting is enabled (50-500). */
  chunk_size?: number | null;
  /** Overrides default temperature if provided. */
  temperature?: number | null;
  /** Overrides default exaggeration if provided. */
  exaggeration?: number | null;
  /** Overrides default CFG weight if provided. */
  cfg_weight?: number | null;
  /** Overrides default seed if provided. */
  seed?: number | null;
  /** Overrides default speed factor if provided. */
  speed_factor?: number | null;
  /** Overrides default language if provided. */
  language?: string | null;
  /** If true, returns a StreamingResponse with WAV audio yielded as each chunk is synthesized. output_format is ignored when streaming. */
  stream?: boolean;
}

export interface OpenAISpeechRequest {
  model: string;
  input: string;
  voice: string;
  response_format?: OpenAIResponseFormat;
  speed?: number;
  seed?: number | null;
  language?: string | null;
}

export interface ErrorResponse {
  detail: string;
}

export interface UpdateStatusResponse {
  message: string;
  restart_needed?: boolean | null;
}

export interface ValidationError {
  loc: (string | integer)[];
  msg: string;
  type: string;
}

export interface HTTPValidationError {
  detail: ValidationError[];
}

export interface PredefinedVoice {
  filename: string;
  display_name?: string;
  [key: string]: string | undefined;
}

/** Parsed SubRip subtitle entry. */
export interface SrtEntry {
  index: number;
  startMs: number;
  endMs: number;
  text: string;
}

/** Generic shape for model-info and initial-data responses. */
export type ChatterboxModelInfo = Record<string, unknown>;
export type ChatterboxInitialData = Record<string, unknown>;

/** Simple wrapper for file upload responses. */
export interface ChatterboxUploadResponse extends Record<string, unknown> {}

/** Generic JSON response from Chatterbox endpoints. */
export type ChatterboxJsonResponse = Record<string, unknown>;

// Re-export integer alias for ValidationError compatibility.
export type integer = number;
