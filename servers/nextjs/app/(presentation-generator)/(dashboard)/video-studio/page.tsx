"use client";

import React, { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { RootState } from "@/store/store";
import { Video, Play, Upload, Loader2, RefreshCw, ExternalLink, Trash2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { notify } from "@/components/ui/sonner";
import {
  VideoStudioApi,
  CreateVideoProjectRequest,
  VideoProject,
  VideoRenderJob,
} from "@/app/(presentation-generator)/services/api/videoStudio";

const POLL_INTERVAL_MS = 2000;

const defaultChatterboxConfig = (url: string) => ({
  chatterbox_url: url || "http://127.0.0.1:8001",
  voice_mode: "predefined",
  predefined_voice_id: "",
  reference_audio_filename: "",
  output_format: "wav",
  speed_factor: 1.0,
  language: "",
});

const defaultYouTubeConfig = {
  title: "",
  description: "",
  tags: [],
  category_id: "22",
  privacy_status: "private",
};

export default function VideoStudioPage() {
  const chatterboxUrl = useSelector(
    (state: RootState) => state.userConfig.llm_config.CHATTERBOX_URL
  );

  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("modern, minimalist");
  const [resolution, setResolution] = useState("1280x720");
  const [fps, setFps] = useState(30);
  const [durationSeconds, setDurationSeconds] = useState(10);
  const [narrationSource, setNarrationSource] = useState("script");
  const [narrationText, setNarrationText] = useState("");
  const [srtContent, setSrtContent] = useState("");
  const [chatterboxConfig, setChatterboxConfig] = useState(
    defaultChatterboxConfig(chatterboxUrl || "")
  );
  const [youtubeConfig, setYoutubeConfig] = useState(defaultYouTubeConfig);
  const [isCreating, setIsCreating] = useState(false);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<VideoRenderJob | null>(null);

  const [youTubeClientId, setYouTubeClientId] = useState("");
  const [youTubeClientSecret, setYouTubeClientSecret] = useState("");
  const [youTubeRedirectUri, setYouTubeRedirectUri] = useState("");
  const [youTubeAuthStatus, setYouTubeAuthStatus] = useState<string>("unknown");
  const [isCheckingYouTube, setIsCheckingYouTube] = useState(false);
  const [isConnectingYouTube, setIsConnectingYouTube] = useState(false);

  useEffect(() => {
    setChatterboxConfig((prev) => ({ ...prev, chatterbox_url: chatterboxUrl || "http://127.0.0.1:8001" }));
  }, [chatterboxUrl]);

  useEffect(() => {
    loadProjects();
    checkYouTubeStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeJobId) return;
    const interval = setInterval(async () => {
      try {
        const job = await VideoStudioApi.getRenderJob(activeJobId);
        setActiveJob(job);
        if (job.status === "completed" || job.status === "failed") {
          clearInterval(interval);
          setActiveJobId(null);
          loadProjects();
          if (job.status === "completed") {
            notify.success("Job complete", job.youtube_video_id
              ? `Uploaded: https://youtu.be/${job.youtube_video_id}`
              : `Rendered to ${job.output_path}`);
          } else {
            notify.error("Job failed", `${job.message || job.error?.detail || "Unknown error"}`);
          }
        }
      } catch (error) {
        console.error("Failed to poll job:", error);
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId]);

  const loadProjects = async () => {
    setIsLoadingProjects(true);
    try {
      const data = await VideoStudioApi.listProjects();
      setProjects(data);
    } catch (error) {
      notify.error("Failed to load projects", error instanceof Error ? error.message : "Unknown");
    } finally {
      setIsLoadingProjects(false);
    }
  };

  const checkYouTubeStatus = async () => {
    setIsCheckingYouTube(true);
    try {
      const status = await VideoStudioApi.getYouTubeAuthStatus();
      setYouTubeAuthStatus(status.status);
    } catch {
      setYouTubeAuthStatus("unknown");
    } finally {
      setIsCheckingYouTube(false);
    }
  };

  const handleCreate = async () => {
    if (!title.trim()) {
      notify.warning("Title required", "Please enter a project title.");
      return;
    }
    const payload: CreateVideoProjectRequest = {
      title,
      description: description || undefined,
      prompt: prompt || undefined,
      style,
      resolution,
      fps,
      duration_seconds: durationSeconds,
      narration_source: narrationSource,
      narration_text: narrationText || undefined,
      srt_content: srtContent || undefined,
      chatterbox_config: {
        ...chatterboxConfig,
        predefined_voice_id: chatterboxConfig.predefined_voice_id || undefined,
        reference_audio_filename: chatterboxConfig.reference_audio_filename || undefined,
        speed_factor: chatterboxConfig.speed_factor || undefined,
        language: chatterboxConfig.language || undefined,
      },
      youtube_config: {
        ...youtubeConfig,
        title: youtubeConfig.title || undefined,
        description: youtubeConfig.description || undefined,
        tags: youtubeConfig.tags,
      },
    };
    setIsCreating(true);
    try {
      const project = await VideoStudioApi.createProject(payload);
      notify.success("Project created", project.title);
      setProjects((prev) => [project, ...prev]);
      setTitle("");
      setDescription("");
      setPrompt("");
      setNarrationText("");
      setSrtContent("");
    } catch (error) {
      notify.error("Create failed", error instanceof Error ? error.message : "Unknown");
    } finally {
      setIsCreating(false);
    }
  };

  const handleRender = async (projectId: string) => {
    try {
      const job = await VideoStudioApi.renderProject(projectId);
      setActiveJobId(job.id);
      setActiveJob(job);
      notify.info("Rendering started", `Job ${job.id}`);
    } catch (error) {
      notify.error("Render failed", error instanceof Error ? error.message : "Unknown");
    }
  };

  const handleUpload = async (projectId: string) => {
    try {
      const job = await VideoStudioApi.uploadToYouTube(projectId);
      setActiveJobId(job.id);
      setActiveJob(job);
      notify.info("Upload started", `Job ${job.id}`);
    } catch (error) {
      notify.error("Upload failed", error instanceof Error ? error.message : "Unknown");
    }
  };

  const handleConnectYouTube = async () => {
    if (!youTubeClientId.trim()) {
      notify.warning("Client ID required", "Enter your Google OAuth client ID.");
      return;
    }
    setIsConnectingYouTube(true);
    try {
      const result = await VideoStudioApi.initiateYouTubeAuth(
        youTubeClientId,
        youTubeClientSecret || undefined,
        youTubeRedirectUri || undefined
      );
      notify.info("OAuth initiated", "Complete authorization in the popup.");
      const popup = window.open(result.url, "youtube-auth", "width=600,height=700");
      if (!popup) {
        notify.warning("Popup blocked", "Please allow popups for YouTube authorization.");
      }

      const poll = setInterval(async () => {
        try {
          const status = await VideoStudioApi.pollYouTubeAuthStatus(result.session_id);
          if (status.status === "success") {
            clearInterval(poll);
            setYouTubeAuthStatus("authenticated");
            notify.success("YouTube connected");
          } else if (status.status === "failed") {
            clearInterval(poll);
            notify.error("YouTube auth failed", status.detail || "Unknown");
          }
        } catch (error) {
          console.error("Failed to poll YouTube auth:", error);
        }
        if (popup?.closed) clearInterval(poll);
      }, 2000);
    } catch (error) {
      notify.error("Initiate failed", error instanceof Error ? error.message : "Unknown");
    } finally {
      setIsConnectingYouTube(false);
    }
  };

  const handleDisconnectYouTube = async () => {
    try {
      await VideoStudioApi.logoutYouTube();
      setYouTubeAuthStatus("not_authenticated");
      notify.success("YouTube disconnected");
    } catch (error) {
      notify.error("Disconnect failed", error instanceof Error ? error.message : "Unknown");
    }
  };

  const formatStatus = (status: string) => {
    switch (status) {
      case "authenticated":
        return "Connected";
      case "not_authenticated":
      case "unknown":
        return "Not connected";
      case "expired":
        return "Expired";
      default:
        return status;
    }
  };

  return (
    <div className="h-screen font-syne flex flex-col overflow-hidden relative">
      <main className="w-full mx-auto overflow-hidden flex flex-col">
        <div className="sticky top-0 right-0 z-50 py-[28px] px-6 backdrop-blur mb-4">
          <div className="flex gap-3 items-center">
            <h3 className="text-[28px] tracking-[-0.84px] font-unbounded font-normal text-black flex items-center gap-2">
              <Video className="h-6 w-6 text-[#7C51F8]" />
              Video Studio
            </h3>
            <p className="text-[10px] px-2.5 py-0.5 rounded-[50px] text-[#7A5AF8] border border-[#EDEEEF] font-medium">
              Beta
            </p>
          </div>
          <p className="mt-1 text-sm text-[#494A4D]">
            Create HTML/CSS animated videos with Chatterbox voiceover and optional YouTube upload.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 pb-24">
          <Tabs defaultValue="create" className="w-full">
            <TabsList className="bg-[#F6F6F9] border border-[#EDEEEF]">
              <TabsTrigger value="create" className="text-xs">
                New project
              </TabsTrigger>
              <TabsTrigger value="projects" className="text-xs">
                Projects
              </TabsTrigger>
              <TabsTrigger value="youtube" className="text-xs">
                YouTube
              </TabsTrigger>
            </TabsList>

            <TabsContent value="create" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Video className="h-5 w-5 text-[#7C51F8]" />
                    New video project
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Describe the video and choose narration settings. The backend will generate an
                    animated HTML scene, render it with Playwright + FFmpeg, and optionally add a
                    Chatterbox voiceover.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Title</Label>
                      <Input
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="My animated video"
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Style</Label>
                      <Input
                        value={style}
                        onChange={(e) => setStyle(e.target.value)}
                        placeholder="modern, minimalist"
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-[#191919]">Description / prompt</Label>
                    <Textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="What should the video be about?"
                      className="min-h-[80px] rounded-[10px] border-[#EDEEEF]"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-[#191919]">LLM prompt (optional)</Label>
                    <Textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="Extra instructions for the HTML animator..."
                      className="min-h-[80px] rounded-[10px] border-[#EDEEEF]"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Resolution</Label>
                      <Input
                        value={resolution}
                        onChange={(e) => setResolution(e.target.value)}
                        placeholder="1280x720"
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">FPS</Label>
                      <Input
                        type="number"
                        value={fps}
                        onChange={(e) => setFps(parseInt(e.target.value, 10) || 30)}
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Duration (seconds)</Label>
                      <Input
                        type="number"
                        step={1}
                        min={1}
                        max={300}
                        value={durationSeconds}
                        onChange={(e) =>
                          setDurationSeconds(parseFloat(e.target.value) || 10)
                        }
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-[#191919]">Narration source</Label>
                    <select
                      value={narrationSource}
                      onChange={(e) => setNarrationSource(e.target.value)}
                      className="w-full rounded-[10px] border border-[#EDEEEF] bg-white px-3 py-2 text-sm"
                    >
                      <option value="script">Script text</option>
                      <option value="srt">SRT subtitles</option>
                      <option value="speaker_notes">Speaker notes (placeholder)</option>
                      <option value="none">No narration</option>
                    </select>
                  </div>

                  {narrationSource === "script" && (
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Narration script</Label>
                      <Textarea
                        value={narrationText}
                        onChange={(e) => setNarrationText(e.target.value)}
                        placeholder="Text to be spoken over the video..."
                        className="min-h-[100px] rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                  )}

                  {narrationSource === "srt" && (
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">SRT content</Label>
                      <Textarea
                        value={srtContent}
                        onChange={(e) => setSrtContent(e.target.value)}
                        placeholder="Paste SRT subtitles here..."
                        className="min-h-[150px] rounded-[10px] border-[#EDEEEF] font-mono text-xs"
                      />
                    </div>
                  )}

                  <div className="rounded-[14px] border border-[#EDEEEF] p-4 space-y-4">
                    <h4 className="text-sm font-medium text-[#191919]">Chatterbox voice</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Server URL</Label>
                        <Input
                          value={chatterboxConfig.chatterbox_url}
                          onChange={(e) =>
                            setChatterboxConfig((prev) => ({
                              ...prev,
                              chatterbox_url: e.target.value,
                            }))
                          }
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Voice mode</Label>
                        <select
                          value={chatterboxConfig.voice_mode}
                          onChange={(e) =>
                            setChatterboxConfig((prev) => ({
                              ...prev,
                              voice_mode: e.target.value,
                            }))
                          }
                          className="w-full rounded-[10px] border border-[#EDEEEF] bg-white px-3 py-2 text-sm"
                        >
                          <option value="predefined">Predefined</option>
                          <option value="clone">Clone</option>
                        </select>
                      </div>
                      {chatterboxConfig.voice_mode === "predefined" ? (
                        <div className="space-y-2">
                          <Label className="text-xs font-medium text-[#191919]">Predefined voice</Label>
                          <Input
                            value={chatterboxConfig.predefined_voice_id}
                            onChange={(e) =>
                              setChatterboxConfig((prev) => ({
                                ...prev,
                                predefined_voice_id: e.target.value,
                              }))
                            }
                            placeholder="Voice filename"
                            className="rounded-[10px] border-[#EDEEEF]"
                          />
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <Label className="text-xs font-medium text-[#191919]">Reference audio</Label>
                          <Input
                            value={chatterboxConfig.reference_audio_filename}
                            onChange={(e) =>
                              setChatterboxConfig((prev) => ({
                                ...prev,
                                reference_audio_filename: e.target.value,
                              }))
                            }
                            placeholder="Reference filename"
                            className="rounded-[10px] border-[#EDEEEF]"
                          />
                        </div>
                      )}
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Output format</Label>
                        <select
                          value={chatterboxConfig.output_format}
                          onChange={(e) =>
                            setChatterboxConfig((prev) => ({
                              ...prev,
                              output_format: e.target.value,
                            }))
                          }
                          className="w-full rounded-[10px] border border-[#EDEEEF] bg-white px-3 py-2 text-sm"
                        >
                          <option value="wav">WAV</option>
                          <option value="mp3">MP3</option>
                          <option value="opus">Opus</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[14px] border border-[#EDEEEF] p-4 space-y-4">
                    <h4 className="text-sm font-medium text-[#191919]">YouTube upload defaults</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Title</Label>
                        <Input
                          value={youtubeConfig.title}
                          onChange={(e) =>
                            setYoutubeConfig((prev) => ({ ...prev, title: e.target.value }))
                          }
                          placeholder="Defaults to project title"
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Privacy</Label>
                        <select
                          value={youtubeConfig.privacy_status}
                          onChange={(e) =>
                            setYoutubeConfig((prev) => ({
                              ...prev,
                              privacy_status: e.target.value,
                            }))
                          }
                          className="w-full rounded-[10px] border border-[#EDEEEF] bg-white px-3 py-2 text-sm"
                        >
                          <option value="private">Private</option>
                          <option value="unlisted">Unlisted</option>
                          <option value="public">Public</option>
                        </select>
                      </div>
                      <div className="space-y-2 md:col-span-2">
                        <Label className="text-xs font-medium text-[#191919]">Description</Label>
                        <Textarea
                          value={youtubeConfig.description}
                          onChange={(e) =>
                            setYoutubeConfig((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                          placeholder="YouTube video description..."
                          className="min-h-[80px] rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <Button
                      onClick={handleCreate}
                      disabled={isCreating}
                      className="rounded-[58px] bg-[#7C51F8] hover:bg-[#6d46e6] text-white px-5"
                    >
                      {isCreating ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Video className="h-4 w-4 mr-2" />
                      )}
                      Create project
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="projects" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7 flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                      <Play className="h-5 w-5 text-[#7C51F8]" />
                      Projects
                    </CardTitle>
                    <CardDescription className="mt-2 text-sm text-[#494A4D]">
                      Rendered videos are saved to the exports directory.
                    </CardDescription>
                  </div>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={loadProjects}
                    disabled={isLoadingProjects}
                    className="rounded-full border-[#EDEEEF]"
                  >
                    <RefreshCw className={`h-4 w-4 ${isLoadingProjects ? "animate-spin" : ""}`} />
                  </Button>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-4">
                  {activeJob && (
                    <div className="rounded-[14px] border border-[#EDEEEF] p-4 space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-[#191919]">
                          {activeJob.job_type === "upload" ? "Uploading to YouTube" : "Rendering video"}
                        </span>
                        <span className="text-[#6B7280]">{activeJob.status}</span>
                      </div>
                      <Progress value={activeJob.progress} className="h-2" />
                      {activeJob.stage && (
                        <p className="text-xs text-[#6B7280]">Stage: {activeJob.stage}</p>
                      )}
                      {activeJob.message && (
                        <p className="text-xs text-red-500">{activeJob.message}</p>
                      )}
                    </div>
                  )}

                  {projects.length === 0 && !isLoadingProjects && (
                    <p className="text-sm text-[#6B7280]">No video projects yet.</p>
                  )}

                  {projects.map((project) => (
                    <div
                      key={project.id}
                      className="rounded-[14px] border border-[#EDEEEF] p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                    >
                      <div>
                        <h4 className="text-sm font-medium text-[#191919]">{project.title}</h4>
                        <p className="text-xs text-[#6B7280] mt-1">Status: {project.status}</p>
                        {project.output_path && (
                          <p className="text-xs text-[#6B7280] truncate max-w-md">
                            {project.output_path}
                          </p>
                        )}
                        {project.youtube_video_id && (
                          <a
                            href={`https://youtu.be/${project.youtube_video_id}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-[#7C51F8] hover:underline flex items-center gap-1 mt-1"
                          >
                            https://youtu.be/{project.youtube_video_id}
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleRender(project.id)}
                          disabled={!!activeJobId}
                          className="rounded-full border-[#EDEEEF]"
                        >
                          <Play className="h-4 w-4 mr-1" />
                          Render
                        </Button>
                        {project.output_path && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleUpload(project.id)}
                            disabled={!!activeJobId || youTubeAuthStatus !== "authenticated"}
                            className="rounded-full border-[#EDEEEF]"
                          >
                            <Upload className="h-4 w-4 mr-1" />
                            Upload
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="youtube" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Upload className="h-5 w-5 text-[#7C51F8]" />
                    YouTube connection
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm text-[#494A4D]">
                    Connect a Google account to upload rendered videos directly to a YouTube channel.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="flex items-center justify-between rounded-[14px] border border-[#EDEEEF] p-4">
                    <div>
                      <p className="text-sm font-medium text-[#191919]">Status</p>
                      <p className="text-xs text-[#6B7280]">
                        {isCheckingYouTube ? "Checking..." : formatStatus(youTubeAuthStatus)}
                      </p>
                    </div>
                    {youTubeAuthStatus === "authenticated" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleDisconnectYouTube}
                        className="rounded-full border-[#EDEEEF]"
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Disconnect
                      </Button>
                    )}
                  </div>

                  {youTubeAuthStatus !== "authenticated" && (
                    <>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Google OAuth client ID</Label>
                        <Input
                          value={youTubeClientId}
                          onChange={(e) => setYouTubeClientId(e.target.value)}
                          placeholder="xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com"
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Client secret (optional)</Label>
                        <Input
                          type="password"
                          value={youTubeClientSecret}
                          onChange={(e) => setYouTubeClientSecret(e.target.value)}
                          placeholder="Leave blank for installed/TV app clients"
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Redirect URI</Label>
                        <Input
                          value={youTubeRedirectUri}
                          onChange={(e) => setYouTubeRedirectUri(e.target.value)}
                          placeholder="http://localhost:8000/api/v1/video-studio/youtube/auth/callback"
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                        <p className="text-[10px] text-[#6B7280]">
                          Must exactly match a URI registered in the Google Cloud Console.
                        </p>
                      </div>
                      <Button
                        onClick={handleConnectYouTube}
                        disabled={isConnectingYouTube}
                        className="rounded-[58px] bg-[#7C51F8] hover:bg-[#6d46e6] text-white px-5"
                      >
                        {isConnectingYouTube ? (
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        ) : (
                          <Upload className="h-4 w-4 mr-2" />
                        )}
                        Connect YouTube
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
