"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Mic,
  Volume2,
  Wand2,
  RefreshCw,
  Loader2,
  Upload,
  Play,
  Pause,
  Server,
  Settings2,
  Radio,
  Trash2,
  Save,
  RotateCcw,
  Power,
  AlertCircle,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notify } from "@/components/ui/sonner";
import { useSelector } from "react-redux";
import { RootState } from "@/store/store";
import Link from "next/link";
import { ChatterboxApi } from "@/app/(presentation-generator)/services/api/chatterbox";
import {
  CustomTTSRequest,
  OpenAISpeechRequest,
  OutputFormat,
  PredefinedVoice,
  VoiceMode,
} from "@/app/(presentation-generator)/services/api/chatterbox-types";

const DEFAULT_OUTPUT_FORMAT: OutputFormat = "wav";

const ChatterboxPage = () => {
  const { CHATTERBOX_URL } = useSelector((state: RootState) => state.userConfig.llm_config);
  const configuredUrl = CHATTERBOX_URL || "Not configured";

  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [referenceFiles, setReferenceFiles] = useState<string[]>([]);
  const [predefinedVoices, setPredefinedVoices] = useState<PredefinedVoice[]>([]);

  const [isLoadingModelInfo, setIsLoadingModelInfo] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingOpenAI, setIsGeneratingOpenAI] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [isUnloading, setIsUnloading] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isResettingSettings, setIsResettingSettings] = useState(false);
  const [isUploadingReference, setIsUploadingReference] = useState(false);
  const [isUploadingVoice, setIsUploadingVoice] = useState(false);

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [openAIAudioUrl, setOpenAIAudioUrl] = useState<string | null>(null);
  const [isOpenAIPlaying, setIsOpenAIPlaying] = useState(false);
  const openAIAudioRef = useRef<HTMLAudioElement | null>(null);

  const [ttsRequest, setTtsRequest] = useState<CustomTTSRequest>({
    text: "",
    voice_mode: "predefined",
    predefined_voice_id: undefined,
    reference_audio_filename: undefined,
    output_format: DEFAULT_OUTPUT_FORMAT,
    split_text: true,
    chunk_size: 120,
    stream: false,
  });

  const [openAIRequest, setOpenAIRequest] = useState<OpenAISpeechRequest>({
    model: "chatterbox",
    input: "",
    voice: "default",
    response_format: "wav",
    speed: 1,
  });

  const [settingsJson, setSettingsJson] = useState<string>("{}");

  const isConfigured = Boolean(CHATTERBOX_URL?.trim());

  const loadModelInfo = async () => {
    if (!isConfigured) return;
    setIsLoadingModelInfo(true);
    try {
      const info = await ChatterboxApi.getModelInfo();
      setModelInfo(info);
    } catch (error) {
      notify.error(
        "Could not reach Chatterbox",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsLoadingModelInfo(false);
    }
  };

  const loadInitialData = async () => {
    if (!isConfigured) return;
    try {
      const data = await ChatterboxApi.getInitialData();
      if (data && typeof data === "object" && "config" in data) {
        setSettingsJson(JSON.stringify(data.config, null, 2));
      }
    } catch (error) {
      console.error("Failed to load initial data:", error);
    }
  };

  const loadReferenceFiles = async () => {
    if (!isConfigured) return;
    try {
      const files = await ChatterboxApi.getReferenceFiles();
      setReferenceFiles(files);
    } catch (error) {
      notify.error(
        "Could not load reference files",
        error instanceof Error ? error.message : "Unknown error"
      );
    }
  };

  const loadPredefinedVoices = async () => {
    if (!isConfigured) return;
    try {
      const voices = await ChatterboxApi.getPredefinedVoices();
      setPredefinedVoices(voices);
    } catch (error) {
      notify.error(
        "Could not load predefined voices",
        error instanceof Error ? error.message : "Unknown error"
      );
    }
  };

  const loadAll = async () => {
    await Promise.all([
      loadModelInfo(),
      loadInitialData(),
      loadReferenceFiles(),
      loadPredefinedVoices(),
    ]);
  };

  useEffect(() => {
    if (isConfigured) {
      loadAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [CHATTERBOX_URL]);

  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (openAIAudioUrl) URL.revokeObjectURL(openAIAudioUrl);
    };
  }, [audioUrl, openAIAudioUrl]);

  const handleGenerateTTS = async () => {
    if (!isConfigured) return;
    if (!ttsRequest.text?.trim()) {
      notify.warning("Text required", "Enter some text to synthesize.");
      return;
    }
    if (ttsRequest.voice_mode === "predefined" && !ttsRequest.predefined_voice_id) {
      notify.warning("Voice required", "Select a predefined voice.");
      return;
    }
    if (ttsRequest.voice_mode === "clone" && !ttsRequest.reference_audio_filename) {
      notify.warning("Reference required", "Select a reference audio file for voice cloning.");
      return;
    }

    setIsGenerating(true);
    try {
      const response = await ChatterboxApi.generateTTS(ttsRequest);
      if (!response.ok) {
        let message = "TTS generation failed";
        try {
          const body = (await response.json()) as { detail?: string };
          if (body.detail) message = body.detail;
        } catch {
          // ignore
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);
      notify.success("Audio generated", "Your TTS audio is ready to play.");
    } catch (error) {
      notify.error(
        "TTS generation failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleGenerateOpenAISpeech = async () => {
    if (!isConfigured) return;
    if (!openAIRequest.input?.trim()) {
      notify.warning("Input required", "Enter some text to synthesize.");
      return;
    }
    setIsGeneratingOpenAI(true);
    try {
      const response = await ChatterboxApi.generateOpenAISpeech(openAIRequest);
      if (!response.ok) {
        let message = "Speech generation failed";
        try {
          const body = (await response.json()) as { detail?: string };
          if (body.detail) message = body.detail;
        } catch {
          // ignore
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      if (openAIAudioUrl) URL.revokeObjectURL(openAIAudioUrl);
      const url = URL.createObjectURL(blob);
      setOpenAIAudioUrl(url);
      notify.success("Speech generated", "Your OpenAI-compatible speech is ready.");
    } catch (error) {
      notify.error(
        "Speech generation failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsGeneratingOpenAI(false);
    }
  };

  const handleUploadReference = async (files: FileList | null) => {
    if (!isConfigured || !files || files.length === 0) return;
    setIsUploadingReference(true);
    try {
      await ChatterboxApi.uploadReference(Array.from(files));
      notify.success("Reference uploaded", "The reference audio has been uploaded.");
      await loadReferenceFiles();
    } catch (error) {
      notify.error(
        "Upload failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsUploadingReference(false);
    }
  };

  const handleUploadPredefinedVoice = async (files: FileList | null) => {
    if (!isConfigured || !files || files.length === 0) return;
    setIsUploadingVoice(true);
    try {
      await ChatterboxApi.uploadPredefinedVoice(Array.from(files));
      notify.success("Voice uploaded", "The predefined voice has been uploaded.");
      await loadPredefinedVoices();
    } catch (error) {
      notify.error(
        "Upload failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsUploadingVoice(false);
    }
  };

  const handleRestartServer = async () => {
    if (!isConfigured) return;
    setIsRestarting(true);
    try {
      const result = await ChatterboxApi.restartServer();
      notify.success("Server restarted", result.message);
      await loadModelInfo();
    } catch (error) {
      notify.error(
        "Restart failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsRestarting(false);
    }
  };

  const handleUnloadModel = async () => {
    if (!isConfigured) return;
    setIsUnloading(true);
    try {
      await ChatterboxApi.unloadModel();
      notify.success("Model unloaded", "The TTS model has been unloaded.");
      setModelInfo(null);
    } catch (error) {
      notify.error(
        "Unload failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsUnloading(false);
    }
  };

  const handleSaveSettings = async () => {
    if (!isConfigured) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(settingsJson);
    } catch {
      notify.warning("Invalid JSON", "Please fix the settings JSON before saving.");
      return;
    }
    setIsSavingSettings(true);
    try {
      const result = await ChatterboxApi.saveSettings(parsed);
      notify.success("Settings saved", result.message);
      await loadInitialData();
    } catch (error) {
      notify.error(
        "Save failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleResetSettings = async () => {
    if (!isConfigured) return;
    setIsResettingSettings(true);
    try {
      const result = await ChatterboxApi.resetSettings();
      notify.success("Settings reset", result.message);
      await loadInitialData();
    } catch (error) {
      notify.error(
        "Reset failed",
        error instanceof Error ? error.message : "Unknown error"
      );
    } finally {
      setIsResettingSettings(false);
    }
  };

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const toggleOpenAIPlay = () => {
    if (!openAIAudioRef.current) return;
    if (isOpenAIPlaying) {
      openAIAudioRef.current.pause();
    } else {
      openAIAudioRef.current.play();
    }
    setIsOpenAIPlaying(!isOpenAIPlaying);
  };

  const updateTts = <K extends keyof CustomTTSRequest>(key: K, value: CustomTTSRequest[K]) => {
    setTtsRequest((prev) => ({ ...prev, [key]: value }));
  };

  const updateOpenAI = <K extends keyof OpenAISpeechRequest>(
    key: K,
    value: OpenAISpeechRequest[K]
  ) => {
    setOpenAIRequest((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="h-screen font-syne flex flex-col overflow-hidden relative">
      <main className="w-full mx-auto overflow-hidden flex flex-col">
        <div className="sticky top-0 right-0 z-50 py-[28px] px-6 backdrop-blur mb-4">
          <div className="flex gap-3 items-center">
            <h3 className="text-[28px] tracking-[-0.84px] font-unbounded font-normal text-black flex items-center gap-2">
              <Volume2 className="h-6 w-6 text-[#7C51F8]" />
              Chatterbox TTS
            </h3>
            <p className="text-[10px] px-2.5 py-0.5 rounded-[50px] text-[#7A5AF8] border border-[#EDEEEF] font-medium">
              {modelInfo ? "Connected" : isConfigured ? "Disconnected" : "Not configured"}
            </p>
          </div>
          <p className="mt-1 text-sm text-[#494A4D]">
            Server:{" "}
            <Link href="/settings" className="text-[#7C51F8] hover:underline">
              {configuredUrl}
            </Link>
          </p>
        </div>

        {!isConfigured && (
          <div className="mx-6 mb-6 rounded-[20px] border border-[#EDEEEF] bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-unbounded text-base font-normal text-black">
                  Chatterbox server URL is not configured
                </h4>
                <p className="mt-1 text-sm text-[#494A4D]">
                  Set the Chatterbox TTS server URL in{" "}
                  <Link href="/settings" className="text-[#7C51F8] hover:underline">
                    Settings
                  </Link>{" "}
                  to start generating speech.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 pb-24">
          <Tabs defaultValue="generate" className="w-full">
            <TabsList className="bg-[#F6F6F9] border border-[#EDEEEF]">
              <TabsTrigger value="generate" className="text-xs">
                Generate
              </TabsTrigger>
              <TabsTrigger value="voices" className="text-xs">
                Voice Library
              </TabsTrigger>
              <TabsTrigger value="server" className="text-xs">
                Server & Settings
              </TabsTrigger>
            </TabsList>

            <TabsContent value="generate" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Mic className="h-5 w-5 text-[#7C51F8]" />
                    Custom TTS
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Generate speech with custom voice and parameters.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-[#191919]">Text</Label>
                    <Textarea
                      placeholder="Enter text to synthesize..."
                      value={ttsRequest.text}
                      onChange={(e) => updateTts("text", e.target.value)}
                      disabled={!isConfigured}
                      className="min-h-[120px] rounded-[10px] border-[#EDEEEF] bg-white text-sm focus-visible:ring-[#7C51F8]"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Voice Mode</Label>
                      <Select
                        value={ttsRequest.voice_mode}
                        onValueChange={(value) => updateTts("voice_mode", value as VoiceMode)}
                        disabled={!isConfigured}
                      >
                        <SelectTrigger className="rounded-[10px] border-[#EDEEEF]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="predefined">Predefined</SelectItem>
                          <SelectItem value="clone">Clone</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {ttsRequest.voice_mode === "predefined" ? (
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">
                          Predefined Voice
                        </Label>
                        <Select
                          value={ttsRequest.predefined_voice_id || ""}
                          onValueChange={(value) => updateTts("predefined_voice_id", value)}
                          disabled={!isConfigured || predefinedVoices.length === 0}
                        >
                          <SelectTrigger className="rounded-[10px] border-[#EDEEEF]">
                            <SelectValue placeholder="Select a voice" />
                          </SelectTrigger>
                          <SelectContent>
                            {predefinedVoices.map((voice) => (
                              <SelectItem key={voice.filename} value={voice.filename}>
                                {voice.display_name || voice.filename}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">
                          Reference Audio
                        </Label>
                        <Select
                          value={ttsRequest.reference_audio_filename || ""}
                          onValueChange={(value) =>
                            updateTts("reference_audio_filename", value)
                          }
                          disabled={!isConfigured || referenceFiles.length === 0}
                        >
                          <SelectTrigger className="rounded-[10px] border-[#EDEEEF]">
                            <SelectValue placeholder="Select reference audio" />
                          </SelectTrigger>
                          <SelectContent>
                            {referenceFiles.map((file) => (
                              <SelectItem key={file} value={file}>
                                {file}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Output Format</Label>
                      <Select
                        value={ttsRequest.output_format}
                        onValueChange={(value) => updateTts("output_format", value as OutputFormat)}
                        disabled={!isConfigured}
                      >
                        <SelectTrigger className="rounded-[10px] border-[#EDEEEF]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="wav">WAV</SelectItem>
                          <SelectItem value="opus">Opus</SelectItem>
                          <SelectItem value="mp3">MP3</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Language</Label>
                      <Input
                        placeholder="auto"
                        value={ttsRequest.language || ""}
                        onChange={(e) => updateTts("language", e.target.value || null)}
                        disabled={!isConfigured}
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                  </div>

                  <div className="space-y-4 rounded-[14px] border border-[#EDEEEF] p-4">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-medium text-[#191919]">Split Text</Label>
                      <Switch
                        checked={!!ttsRequest.split_text}
                        onCheckedChange={(checked) => updateTts("split_text", checked)}
                        disabled={!isConfigured}
                      />
                    </div>

                    {ttsRequest.split_text && (
                      <div className="space-y-2">
                        <div className="flex justify-between">
                          <Label className="text-xs font-medium text-[#191919]">Chunk Size</Label>
                          <span className="text-xs text-[#6B7280]">{ttsRequest.chunk_size}</span>
                        </div>
                        <Slider
                          value={[ttsRequest.chunk_size || 120]}
                          onValueChange={([value]) => updateTts("chunk_size", value)}
                          min={50}
                          max={500}
                          step={10}
                          disabled={!isConfigured}
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Speed Factor</Label>
                        <Input
                          type="number"
                          step={0.1}
                          placeholder="1.0"
                          value={ttsRequest.speed_factor ?? ""}
                          onChange={(e) =>
                            updateTts(
                              "speed_factor",
                              e.target.value === "" ? null : parseFloat(e.target.value)
                            )
                          }
                          disabled={!isConfigured}
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Temperature</Label>
                        <Input
                          type="number"
                          step={0.1}
                          placeholder="auto"
                          value={ttsRequest.temperature ?? ""}
                          onChange={(e) =>
                            updateTts(
                              "temperature",
                              e.target.value === "" ? null : parseFloat(e.target.value)
                            )
                          }
                          disabled={!isConfigured}
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Exaggeration</Label>
                        <Input
                          type="number"
                          step={0.1}
                          placeholder="auto"
                          value={ttsRequest.exaggeration ?? ""}
                          onChange={(e) =>
                            updateTts(
                              "exaggeration",
                              e.target.value === "" ? null : parseFloat(e.target.value)
                            )
                          }
                          disabled={!isConfigured}
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">CFG Weight</Label>
                        <Input
                          type="number"
                          step={0.1}
                          placeholder="auto"
                          value={ttsRequest.cfg_weight ?? ""}
                          onChange={(e) =>
                            updateTts(
                              "cfg_weight",
                              e.target.value === "" ? null : parseFloat(e.target.value)
                            )
                          }
                          disabled={!isConfigured}
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-[#191919]">Seed</Label>
                        <Input
                          type="number"
                          placeholder="auto"
                          value={ttsRequest.seed ?? ""}
                          onChange={(e) =>
                            updateTts(
                              "seed",
                              e.target.value === "" ? null : parseInt(e.target.value, 10)
                            )
                          }
                          disabled={!isConfigured}
                          className="rounded-[10px] border-[#EDEEEF]"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={!!ttsRequest.stream}
                        onCheckedChange={(checked) => updateTts("stream", checked)}
                        disabled={!isConfigured}
                      />
                      <Label className="text-xs font-medium text-[#191919]">Stream audio</Label>
                    </div>
                    <Button
                      onClick={handleGenerateTTS}
                      disabled={!isConfigured || isGenerating}
                      className="rounded-[58px] bg-[#7C51F8] hover:bg-[#6d46e6] text-white px-5"
                    >
                      {isGenerating ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Wand2 className="h-4 w-4 mr-2" />
                      )}
                      Generate
                    </Button>
                  </div>

                  {audioUrl && (
                    <div className="rounded-[14px] border border-[#EDEEEF] p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={togglePlay}
                          className="rounded-full border-[#EDEEEF]"
                        >
                          {isPlaying ? (
                            <Pause className="h-4 w-4" />
                          ) : (
                            <Play className="h-4 w-4" />
                          )}
                        </Button>
                        <span className="text-sm text-[#191919]">Generated audio</span>
                      </div>
                      <audio
                        ref={audioRef}
                        src={audioUrl}
                        onEnded={() => setIsPlaying(false)}
                        className="w-full"
                        controls
                      />
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Radio className="h-5 w-5 text-[#7C51F8]" />
                    OpenAI-Compatible Speech
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Use the /v1/audio/speech endpoint compatible with OpenAI clients.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-[#191919]">Input</Label>
                    <Textarea
                      placeholder="Enter text to synthesize..."
                      value={openAIRequest.input}
                      onChange={(e) => updateOpenAI("input", e.target.value)}
                      disabled={!isConfigured}
                      className="min-h-[100px] rounded-[10px] border-[#EDEEEF] bg-white text-sm focus-visible:ring-[#7C51F8]"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Model</Label>
                      <Input
                        value={openAIRequest.model}
                        onChange={(e) => updateOpenAI("model", e.target.value)}
                        disabled={!isConfigured}
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Voice</Label>
                      <Input
                        value={openAIRequest.voice}
                        onChange={(e) => updateOpenAI("voice", e.target.value)}
                        disabled={!isConfigured}
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Response Format</Label>
                      <Select
                        value={openAIRequest.response_format}
                        onValueChange={(value) =>
                          updateOpenAI("response_format", value as OutputFormat)
                        }
                        disabled={!isConfigured}
                      >
                        <SelectTrigger className="rounded-[10px] border-[#EDEEEF]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="wav">WAV</SelectItem>
                          <SelectItem value="opus">Opus</SelectItem>
                          <SelectItem value="mp3">MP3</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-[#191919]">Speed</Label>
                      <Input
                        type="number"
                        step={0.1}
                        min={0.25}
                        max={4}
                        value={openAIRequest.speed}
                        onChange={(e) =>
                          updateOpenAI("speed", parseFloat(e.target.value) || 1)
                        }
                        disabled={!isConfigured}
                        className="rounded-[10px] border-[#EDEEEF]"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <Button
                      onClick={handleGenerateOpenAISpeech}
                      disabled={!isConfigured || isGeneratingOpenAI}
                      className="rounded-[58px] bg-[#7C51F8] hover:bg-[#6d46e6] text-white px-5"
                    >
                      {isGeneratingOpenAI ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Wand2 className="h-4 w-4 mr-2" />
                      )}
                      Generate Speech
                    </Button>
                  </div>

                  {openAIAudioUrl && (
                    <div className="rounded-[14px] border border-[#EDEEEF] p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={toggleOpenAIPlay}
                          className="rounded-full border-[#EDEEEF]"
                        >
                          {isOpenAIPlaying ? (
                            <Pause className="h-4 w-4" />
                          ) : (
                            <Play className="h-4 w-4" />
                          )}
                        </Button>
                        <span className="text-sm text-[#191919]">Generated speech</span>
                      </div>
                      <audio
                        ref={openAIAudioRef}
                        src={openAIAudioUrl}
                        onEnded={() => setIsOpenAIPlaying(false)}
                        className="w-full"
                        controls
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="voices" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Mic className="h-5 w-5 text-[#7C51F8]" />
                    Predefined Voices
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Built-in voices available on the Chatterbox server. Upload new .wav or .mp3
                    files to add voices.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      onClick={loadPredefinedVoices}
                      disabled={!isConfigured || isLoadingModelInfo}
                      className="rounded-[58px] border-[#EDEEEF] text-xs"
                    >
                      <RefreshCw className="h-3.5 w-3.5 mr-2" />
                      Refresh
                    </Button>
                    <Label
                      htmlFor="upload-predefined-voice"
                      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-[58px] border border-[#EDEEEF] bg-white px-4 py-2 text-xs font-medium transition hover:bg-[#F6F6F9] ${
                        !isConfigured || isUploadingVoice ? "opacity-50 cursor-not-allowed" : ""
                      }`}
                    >
                      {isUploadingVoice ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Upload className="h-3.5 w-3.5" />
                      )}
                      Upload voice
                    </Label>
                    <Input
                      id="upload-predefined-voice"
                      type="file"
                      accept=".wav,.mp3,audio/wav,audio/mpeg"
                      multiple
                      onChange={(e) => handleUploadPredefinedVoice(e.target.files)}
                      disabled={!isConfigured || isUploadingVoice}
                      className="hidden"
                    />
                  </div>

                  {predefinedVoices.length === 0 ? (
                    <p className="text-sm text-[#6B7280]">No predefined voices found.</p>
                  ) : (
                    <ul className="divide-y divide-[#EDEEEF]">
                      {predefinedVoices.map((voice) => (
                        <li
                          key={voice.filename}
                          className="flex items-center justify-between py-3 text-sm"
                        >
                          <span className="text-[#191919]">
                            {voice.display_name || voice.filename}
                          </span>
                          <span className="text-xs text-[#6B7280]">{voice.filename}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Upload className="h-5 w-5 text-[#7C51F8]" />
                    Reference Audio
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Reference audio files used for voice cloning.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      onClick={loadReferenceFiles}
                      disabled={!isConfigured || isLoadingModelInfo}
                      className="rounded-[58px] border-[#EDEEEF] text-xs"
                    >
                      <RefreshCw className="h-3.5 w-3.5 mr-2" />
                      Refresh
                    </Button>
                    <Label
                      htmlFor="upload-reference"
                      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-[58px] border border-[#EDEEEF] bg-white px-4 py-2 text-xs font-medium transition hover:bg-[#F6F6F9] ${
                        !isConfigured || isUploadingReference ? "opacity-50 cursor-not-allowed" : ""
                      }`}
                    >
                      {isUploadingReference ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Upload className="h-3.5 w-3.5" />
                      )}
                      Upload reference
                    </Label>
                    <Input
                      id="upload-reference"
                      type="file"
                      accept=".wav,.mp3,audio/wav,audio/mpeg"
                      multiple
                      onChange={(e) => handleUploadReference(e.target.files)}
                      disabled={!isConfigured || isUploadingReference}
                      className="hidden"
                    />
                  </div>

                  {referenceFiles.length === 0 ? (
                    <p className="text-sm text-[#6B7280]">No reference audio files found.</p>
                  ) : (
                    <ul className="divide-y divide-[#EDEEEF]">
                      {referenceFiles.map((file) => (
                        <li key={file} className="flex items-center justify-between py-3 text-sm">
                          <span className="text-[#191919]">{file}</span>
                          <Trash2 className="h-4 w-4 text-[#9CA3AF]" />
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="server" className="space-y-6 mt-6">
              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Server className="h-5 w-5 text-[#7C51F8]" />
                    Model Status
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Current Chatterbox model information and server controls.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      onClick={loadModelInfo}
                      disabled={!isConfigured || isLoadingModelInfo}
                      className="rounded-[58px] border-[#EDEEEF] text-xs"
                    >
                      {isLoadingModelInfo ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5 mr-2" />
                      )}
                      Refresh
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleRestartServer}
                      disabled={!isConfigured || isRestarting}
                      className="rounded-[58px] border-[#EDEEEF] text-xs"
                    >
                      {isRestarting ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />
                      ) : (
                        <RotateCcw className="h-3.5 w-3.5 mr-2" />
                      )}
                      Restart Server
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleUnloadModel}
                      disabled={!isConfigured || isUnloading}
                      className="rounded-[58px] border-[#EDEEEF] text-xs text-red-600 hover:text-red-700"
                    >
                      {isUnloading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-2" />
                      ) : (
                        <Power className="h-3.5 w-3.5 mr-2" />
                      )}
                      Unload Model
                    </Button>
                  </div>

                  {modelInfo ? (
                    <pre className="rounded-[10px] bg-[#F6F6F9] p-4 text-xs text-[#191919] overflow-auto max-h-[300px]">
                      {JSON.stringify(modelInfo, null, 2)}
                    </pre>
                  ) : (
                    <p className="text-sm text-[#6B7280]">
                      {isConfigured
                        ? "No model info loaded. Click Refresh to connect."
                        : "Configure the Chatterbox URL to view model status."}
                    </p>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
                <CardHeader className="p-7">
                  <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                    <Settings2 className="h-5 w-5 text-[#7C51F8]" />
                    Server Settings
                  </CardTitle>
                  <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                    Edit and save the Chatterbox server configuration. Invalid JSON will be rejected.
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-7 pt-0 space-y-5">
                  <Textarea
                    value={settingsJson}
                    onChange={(e) => setSettingsJson(e.target.value)}
                    disabled={!isConfigured}
                    className="min-h-[240px] rounded-[10px] border-[#EDEEEF] bg-white font-mono text-xs focus-visible:ring-[#7C51F8]"
                  />
                  <div className="flex items-center gap-3">
                    <Button
                      onClick={handleSaveSettings}
                      disabled={!isConfigured || isSavingSettings}
                      className="rounded-[58px] bg-[#7C51F8] hover:bg-[#6d46e6] text-white px-5"
                    >
                      {isSavingSettings ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <Save className="h-4 w-4 mr-2" />
                      )}
                      Save Settings
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleResetSettings}
                      disabled={!isConfigured || isResettingSettings}
                      className="rounded-[58px] border-[#EDEEEF]"
                    >
                      {isResettingSettings ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                      ) : (
                        <RotateCcw className="h-4 w-4 mr-2" />
                      )}
                      Reset to Defaults
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </main>
    </div>
  );
};

export default ChatterboxPage;
