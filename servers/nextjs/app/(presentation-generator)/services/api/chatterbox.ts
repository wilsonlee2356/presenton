import { store } from "@/store/store";
import {
  CustomTTSRequest,
  OpenAISpeechRequest,
  UpdateStatusResponse,
  PredefinedVoice,
  ChatterboxModelInfo,
  ChatterboxInitialData,
  ChatterboxUploadResponse,
  ChatterboxJsonResponse,
  ErrorResponse,
} from "./chatterbox-types";

function getChatterboxBaseUrl(): string {
  const url =
    store.getState().userConfig.llm_config.CHATTERBOX_URL?.trim() ||
    "http://127.0.0.1:8001";
  return url.replace(/\/$/, "");
}

function joinUrl(path: string): string {
  return `${getChatterboxBaseUrl()}${path}`;
}

async function handleJsonResponse<T>(
  response: Response,
  defaultError = "Chatterbox request failed"
): Promise<T> {
  if (!response.ok) {
    let message = defaultError;
    try {
      const body = (await response.json()) as ErrorResponse | { detail?: unknown };
      if (body.detail) {
        message =
          typeof body.detail === "string"
            ? body.detail
            : Array.isArray(body.detail)
              ? body.detail.map((err) => `${err.loc?.join(".")}: ${err.msg}`).join("; ")
              : defaultError;
      }
    } catch {
      // ignore parse failure
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export class ChatterboxApi {
  static getModelInfo(): Promise<ChatterboxModelInfo> {
    return fetch(joinUrl("/api/model-info")).then((res) =>
      handleJsonResponse<ChatterboxModelInfo>(res, "Failed to fetch model info")
    );
  }

  static getInitialData(): Promise<ChatterboxInitialData> {
    return fetch(joinUrl("/api/ui/initial-data")).then((res) =>
      handleJsonResponse<ChatterboxInitialData>(res, "Failed to fetch initial data")
    );
  }

  static saveSettings(settings: Record<string, unknown>): Promise<UpdateStatusResponse> {
    return fetch(joinUrl("/save_settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then((res) =>
      handleJsonResponse<UpdateStatusResponse>(res, "Failed to save settings")
    );
  }

  static resetSettings(): Promise<UpdateStatusResponse> {
    return fetch(joinUrl("/reset_settings"), {
      method: "POST",
    }).then((res) =>
      handleJsonResponse<UpdateStatusResponse>(res, "Failed to reset settings")
    );
  }

  static restartServer(): Promise<UpdateStatusResponse> {
    return fetch(joinUrl("/restart_server"), {
      method: "POST",
    }).then((res) =>
      handleJsonResponse<UpdateStatusResponse>(res, "Failed to restart server")
    );
  }

  static unloadModel(): Promise<ChatterboxJsonResponse> {
    return fetch(joinUrl("/api/unload"), {
      method: "POST",
    }).then((res) =>
      handleJsonResponse<ChatterboxJsonResponse>(res, "Failed to unload model")
    );
  }

  static getReferenceFiles(): Promise<string[]> {
    return fetch(joinUrl("/get_reference_files")).then((res) =>
      handleJsonResponse<string[]>(res, "Failed to fetch reference files")
    );
  }

  static getPredefinedVoices(): Promise<PredefinedVoice[]> {
    return fetch(joinUrl("/get_predefined_voices")).then((res) =>
      handleJsonResponse<PredefinedVoice[]>(res, "Failed to fetch predefined voices")
    );
  }

  static uploadReference(files: File[]): Promise<ChatterboxUploadResponse> {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return fetch(joinUrl("/upload_reference"), {
      method: "POST",
      body: formData,
    }).then((res) =>
      handleJsonResponse<ChatterboxUploadResponse>(res, "Failed to upload reference audio")
    );
  }

  static uploadPredefinedVoice(files: File[]): Promise<ChatterboxUploadResponse> {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return fetch(joinUrl("/upload_predefined_voice"), {
      method: "POST",
      body: formData,
    }).then((res) =>
      handleJsonResponse<ChatterboxUploadResponse>(res, "Failed to upload predefined voice")
    );
  }

  /**
   * Returns the raw Response so the caller can decide whether to stream or
   * read the full blob.
   */
  static generateTTS(request: CustomTTSRequest): Promise<Response> {
    return fetch(joinUrl("/tts"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  }

  static getOpenAIVoices(model?: string): Promise<Record<string, unknown>> {
    const url = new URL(joinUrl("/v1/audio/voices"));
    if (model) {
      url.searchParams.set("model", model);
    }
    return fetch(url.toString()).then((res) =>
      handleJsonResponse<Record<string, unknown>>(res, "Failed to fetch voices")
    );
  }

  /**
   * Returns the raw Response so the caller can read the audio blob.
   */
  static generateOpenAISpeech(request: OpenAISpeechRequest): Promise<Response> {
    return fetch(joinUrl("/v1/audio/speech"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  }
}
