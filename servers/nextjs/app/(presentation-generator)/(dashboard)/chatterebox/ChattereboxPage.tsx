"use client";

import React from "react";
import { Mic, Volume2, Wand2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const ChattereboxPage = () => {
  return (
    <div className="h-screen font-syne flex flex-col overflow-hidden relative">
      <main className="w-full mx-auto overflow-hidden flex flex-col">
        <div className="sticky top-0 right-0 z-50 py-[28px] px-6 backdrop-blur mb-4">
          <div className="flex gap-3 items-center">
            <h3 className="text-[28px] tracking-[-0.84px] font-unbounded font-normal text-black flex items-center gap-2">
              <Volume2 className="h-6 w-6 text-[#7C51F8]" />
              Chatterebox TTS
            </h3>
            <p className="text-[10px] px-2.5 py-0.5 rounded-[50px] text-[#7A5AF8] border border-[#EDEEEF] font-medium">
              Coming soon
            </p>
          </div>
        </div>

        <div className="grid gap-6 max-w-3xl px-6 py-8">
          <Card className="rounded-[20px] border border-[#EDEEEF] bg-white shadow-sm">
            <CardHeader className="p-7">
              <CardTitle className="font-unbounded text-lg font-normal text-black flex items-center gap-2">
                <Mic className="h-5 w-5 text-[#7C51F8]" />
                Text-to-Speech integration
              </CardTitle>
              <CardDescription className="mt-2 text-sm leading-relaxed text-[#494A4D]">
                This page will connect to the Chatterebox TTS server to generate
                natural-sounding voiceovers for your presentations.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-7 pt-0">
              <ul className="space-y-3 text-sm text-[#494A4D]">
                <li className="flex items-start gap-3">
                  <Wand2 className="h-4 w-4 text-[#7C51F8] mt-0.5 shrink-0" />
                  <span>Convert slide notes and scripts into spoken audio.</span>
                </li>
                <li className="flex items-start gap-3">
                  <Wand2 className="h-4 w-4 text-[#7C51F8] mt-0.5 shrink-0" />
                  <span>Pick from multiple voices and speaking styles.</span>
                </li>
                <li className="flex items-start gap-3">
                  <Wand2 className="h-4 w-4 text-[#7C51F8] mt-0.5 shrink-0" />
                  <span>Sync generated audio directly with your slides.</span>
                </li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default ChattereboxPage;
