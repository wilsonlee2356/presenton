import { getApiUrl } from "@/utils/api";

export interface ChatterboxConfigInput {
  chatterbox_url: string;
  voice_mode: string;
  predefined_voice_id?: string;
  reference_audio_filename?: string;
  output_format: string;
  speed_factor?: number | null;
  language?: string | null;
}

export interface YouTubeConfigInput {
  title?: string;
  description?: string;
  tags: string[];
  category_id?: string;
  privacy_status?: string;
}

export interface CreateVideoProjectRequest {
  title: string;
  description?: string;
  prompt?: string;
  template?: string;
  style?: string;
  resolution?: string;
  fps: number;
  duration_seconds: number;
  narration_source?: string;
  narration_text?: string;
  srt_content?: string;
  chatterbox_config: ChatterboxConfigInput;
  youtube_config: YouTubeConfigInput;
}

export interface VideoProject {
  id: string;
  title: string;
  description?: string;
  status: string;
  output_path?: string;
  youtube_video_id?: string;
  created_at: string;
  updated_at: string;
}

export interface VideoRenderJob {
  id: string;
  project_id: string;
  job_type: string;
  status: string;
  stage?: string;
  progress: number;
  message?: string;
  error?: Record<string, unknown>;
  output_path?: string;
  youtube_video_id?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(getApiUrl(`/api/v1/video-studio${path}`), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const VideoStudioApi = {
  createProject: (payload: CreateVideoProjectRequest) =>
    request<VideoProject>("/projects", { method: "POST", body: JSON.stringify(payload) }),

  listProjects: () => request<VideoProject[]>("/projects"),

  getProject: (id: string) => request<VideoProject>(`/projects/${id}`),

  renderProject: (id: string) =>
    request<VideoRenderJob>(`/projects/${id}/render`, { method: "POST" }),

  getRenderJob: (id: string) => request<VideoRenderJob>(`/render-jobs/${id}`),

  uploadToYouTube: (id: string) =>
    request<VideoRenderJob>(`/projects/${id}/upload-youtube`, { method: "POST" }),

  initiateYouTubeAuth: (clientId: string, clientSecret?: string, redirectUri?: string) =>
    request<{ session_id: string; url: string; redirect_uri: string; instructions: string }>(
      "/youtube/auth/initiate",
      {
        method: "POST",
        body: JSON.stringify({
          client_id: clientId,
          client_secret: clientSecret || "",
          redirect_uri: redirectUri || "",
        }),
      }
    ),

  pollYouTubeAuthStatus: (sessionId: string) =>
    request<{ status: string; detail?: string }>(`/youtube/auth/status/${sessionId}`),

  getYouTubeAuthStatus: () =>
    request<{ status: string; detail?: string }>("/youtube/auth/status"),

  logoutYouTube: () =>
    request<{ status: string; detail?: string }>("/youtube/auth/logout", { method: "POST" }),
};
