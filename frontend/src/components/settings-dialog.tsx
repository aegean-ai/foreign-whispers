"use client";

import { useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  SettingsIcon,
  XIcon,
  DownloadIcon,
  MicIcon,
  LanguagesIcon,
  Volume2Icon,
  ScissorsIcon,
  AlignCenterHorizontalIcon,
  CircleDotIcon,
  CircleIcon,
} from "lucide-react";
import { useStudioSettingsContext } from "@/contexts/studio-settings-context";

type SettingsSection = "download" | "transcribe" | "translate" | "alignment" | "tts" | "stitch";

const SECTIONS: { key: SettingsSection; label: string; icon: React.ElementType }[] = [
  { key: "download", label: "Download", icon: DownloadIcon },
  { key: "transcribe", label: "Transcribe", icon: MicIcon },
  { key: "translate", label: "Translate", icon: LanguagesIcon },
  { key: "alignment", label: "Alignment", icon: AlignCenterHorizontalIcon },
  { key: "tts", label: "TTS", icon: Volume2Icon },
  { key: "stitch", label: "Stitch", icon: ScissorsIcon },
];

function DownloadSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Auto-fetch captions</p>
          <p className="text-xs text-muted-foreground">Download YouTube closed captions when available.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Always on</span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Video quality</p>
          <p className="text-xs text-muted-foreground">yt-dlp downloads the best available quality.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Best available</span>
      </div>
    </div>
  );
}

function TranscribeSettings() {
  const { settings, toggleUseYoutubeCaptions } = useStudioSettingsContext();
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">STT model</p>
          <p className="text-xs text-muted-foreground">Whisper model used for transcription.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">faster-whisper-medium</span>
      </div>
      <Separator />
      <div className="flex items-start gap-3">
        <Checkbox id="use-yt-captions" checked={settings.useYoutubeCaptions} onCheckedChange={toggleUseYoutubeCaptions} className="mt-0.5" />
        <div>
          <Label htmlFor="use-yt-captions" className="text-sm font-medium cursor-pointer">Use YouTube Captions</Label>
          <p className="text-xs text-muted-foreground mt-1">
            When available, use YouTube's closed captions instead of running Whisper.
            Uncheck to always run Whisper STT.
          </p>
        </div>
      </div>
    </div>
  );
}

function TranslateSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Translation engine</p>
          <p className="text-xs text-muted-foreground">Offline translation using argostranslate.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">argostranslate</span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Target language</p>
          <p className="text-xs text-muted-foreground">Default target language for translation.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Spanish (es)</span>
      </div>
    </div>
  );
}

const ALIGNMENT_METHODS = [
  { value: "baseline", label: "Baseline", description: "No temporal alignment — TTS audio plays at natural speed." },
  { value: "aligned", label: "Aligned", description: "Syllable-based stretch/compress to match original segment timing." },
];

function AlignmentSettings() {
  const { settings, toggleSetting } = useStudioSettingsContext();
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium">Dubbing method</p>
        <p className="text-xs text-muted-foreground mt-1">Select one or more. Multiple selections produce separate output variants.</p>
      </div>
      {ALIGNMENT_METHODS.map((m) => (
        <button
          type="button"
          key={m.value}
          className="flex w-full cursor-pointer items-center gap-3 rounded-md border border-border/40 p-3 text-left transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
          data-checked={settings.dubbing.includes(m.value)}
          onClick={() => toggleSetting("dubbing", m.value)}
        >
          {settings.dubbing.includes(m.value) ? (
            <CircleDotIcon className="size-4 shrink-0 text-primary" />
          ) : (
            <CircleIcon className="size-4 shrink-0 text-muted-foreground" />
          )}
          <div>
            <div className="text-sm font-medium">{m.label}</div>
            <div className="text-xs text-muted-foreground">{m.description}</div>
          </div>
        </button>
      ))}
    </div>
  );
}

const DIARIZATION_METHODS = [
  { value: "pyannote", label: "pyannote", description: "Speaker diarization via pyannote.audio" },
];

const VOICE_CLONING_METHODS = [
  { value: "chatterbox", label: "Chatterbox", description: "Voice cloning via Chatterbox (Resemble AI)" },
];

function TTSSettings() {
  const { settings, toggleSetting } = useStudioSettingsContext();
  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">TTS engine</p>
          <p className="text-xs text-muted-foreground">Model used for speech synthesis.</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Chatterbox</span>
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-sm font-medium">Diarization</p>
        <p className="text-xs text-muted-foreground">Speaker detection method for multi-speaker videos.</p>
        {DIARIZATION_METHODS.map((m) => (
          <button
            type="button"
            key={m.value}
            className="flex w-full cursor-pointer items-center gap-3 rounded-md border border-border/40 p-3 text-left transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
            data-checked={settings.diarization.includes(m.value)}
            onClick={() => toggleSetting("diarization", m.value)}
          >
            {settings.diarization.includes(m.value) ? (
              <CircleDotIcon className="size-4 shrink-0 text-primary" />
            ) : (
              <CircleIcon className="size-4 shrink-0 text-muted-foreground" />
            )}
            <div>
              <div className="text-sm font-medium">{m.label}</div>
              <div className="text-xs text-muted-foreground">{m.description}</div>
            </div>
          </button>
        ))}
      </div>

      <Separator />

      <div className="space-y-3">
        <p className="text-sm font-medium">Voice Cloning</p>
        <p className="text-xs text-muted-foreground">Method for cloning the source speaker's voice.</p>
        {VOICE_CLONING_METHODS.map((m) => (
          <button
            type="button"
            key={m.value}
            className="flex w-full cursor-pointer items-center gap-3 rounded-md border border-border/40 p-3 text-left transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
            data-checked={settings.voiceCloning.includes(m.value)}
            onClick={() => toggleSetting("voiceCloning", m.value)}
          >
            {settings.voiceCloning.includes(m.value) ? (
              <CircleDotIcon className="size-4 shrink-0 text-primary" />
            ) : (
              <CircleIcon className="size-4 shrink-0 text-muted-foreground" />
            )}
            <div>
              <div className="text-sm font-medium">{m.label}</div>
              <div className="text-xs text-muted-foreground">{m.description}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StitchSettings() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Caption style</p>
          <p className="text-xs text-muted-foreground">Rolling two-line captions (Google-style bridge display).</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Two-line rolling</span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Video encoder</p>
          <p className="text-xs text-muted-foreground">Audio-only remux via ffmpeg (no re-encoding).</p>
        </div>
        <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">ffmpeg remux</span>
      </div>
    </div>
  );
}

const SECTION_CONTENT: Record<SettingsSection, { title: string; description: string; component: React.FC }> = {
  download: { title: "Download", description: "Video download and caption fetching.", component: DownloadSettings },
  transcribe: { title: "Transcribe", description: "Speech-to-text via Whisper.", component: TranscribeSettings },
  translate: { title: "Translate", description: "Source-to-target language translation.", component: TranslateSettings },
  alignment: { title: "Alignment", description: "Temporal alignment between source and dubbed audio.", component: AlignmentSettings },
  tts: { title: "TTS", description: "Text-to-speech synthesis and voice configuration.", component: TTSSettings },
  stitch: { title: "Stitch", description: "Final video assembly.", component: StitchSettings },
};

export function SettingsDialog() {
  const [activeSection, setActiveSection] = useState<SettingsSection>("download");
  const { title, description, component: Content } = SECTION_CONTENT[activeSection];

  return (
    <Dialog.Root>
      <Dialog.Trigger
        render={
          <Button variant="outline" size="icon" />
        }
      >
        <SettingsIcon className="size-4" />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/50 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 supports-backdrop-filter:backdrop-blur-sm" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl transition duration-200 data-ending-style:opacity-0 data-ending-style:scale-95 data-starting-style:opacity-0 data-starting-style:scale-95 w-[720px] max-h-[80vh]">
          <div className="flex h-[560px]">
            {/* Sidebar nav */}
            <nav className="w-48 border-r p-4 flex flex-col gap-1 shrink-0">
              <Dialog.Title className="text-sm font-semibold mb-3 px-2">Settings</Dialog.Title>
              {SECTIONS.map(({ key, label, icon: Icon }) => (
                <button
                  type="button"
                  key={key}
                  onClick={() => setActiveSection(key)}
                  className={`flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                    activeSection === key
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                  }`}
                >
                  <Icon className="size-3.5" />
                  {label}
                </button>
              ))}
            </nav>

            {/* Content area */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="mb-1">
                <h3 className="text-lg font-medium">{title}</h3>
                <Dialog.Description className="text-sm text-muted-foreground">{description}</Dialog.Description>
              </div>
              <Separator className="my-4" />
              <Content />
            </div>
          </div>

          {/* Close button */}
          <Dialog.Close
            render={
              <Button variant="ghost" size="icon-sm" className="absolute top-3 right-3" />
            }
          >
            <XIcon />
            <span className="sr-only">Close</span>
          </Dialog.Close>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
