"use client";

import { Loader2, Plus, Trash2, Upload, X } from "lucide-react";
import { MediaAsset, TimelineClip } from "@/lib/types";

interface MediaTrayProps {
    assets: MediaAsset[];
    clips: TimelineClip[];
    uploading: boolean;
    onUpload: () => void;
    onPlace: (asset: MediaAsset) => void;
    onDeleteAsset: (asset: MediaAsset) => void;
    onClose: () => void;
}

export function MediaTray({ assets, clips, uploading, onUpload, onPlace, onDeleteAsset, onClose }: MediaTrayProps) {
    return (
        <section className="absolute inset-x-0 bottom-[264px] z-40 h-44 border-y border-[#383835] bg-[#1b1b1a]/98 px-4 py-3 shadow-2xl backdrop-blur-xl">
            <div className="mb-2 flex items-center">
                <div>
                    <h3 className="text-[12px] font-medium text-[#e6e2db]">Project media</h3>
                    <p className="text-[10px] text-[#77736d]">Choose an image to place it at the playhead.</p>
                </div>
                <div className="flex-1" />
                <button type="button" onClick={onClose} className="rounded-md p-1.5 text-[#77736d] hover:bg-white/5 hover:text-[#d8d4cd]" aria-label="Close media tray">
                    <X className="h-4 w-4" />
                </button>
            </div>

            <div className="flex h-28 gap-2 overflow-x-auto pb-1">
                <button
                    type="button"
                    onClick={onUpload}
                    disabled={uploading}
                    className="flex w-28 shrink-0 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[#4a4a47] bg-[#222220] text-[10px] text-[#8a867f] hover:border-[#68645e] hover:text-[#d0ccc5] disabled:opacity-60"
                >
                    {uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Upload className="h-5 w-5" />}
                    {uploading ? "Processing…" : "Upload image"}
                </button>

                {assets.map((asset) => {
                    const used = clips.some((clip) => clip.asset_id === asset.id);
                    return (
                        <div key={asset.id} className="group relative w-28 shrink-0 overflow-hidden rounded-lg bg-[#272725]">
                            <button type="button" onClick={() => onPlace(asset)} className="block h-full w-full text-left">
                                <img src={asset.access_url} crossOrigin="use-credentials" alt="" className="h-20 w-full object-cover" />
                                <span className="block truncate px-2 py-1.5 text-[9px] text-[#aaa69f]">{asset.original_filename}</span>
                                <span className="absolute right-1.5 top-1.5 rounded-full bg-black/65 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100">
                                    <Plus className="h-3 w-3" />
                                </span>
                            </button>
                            <button
                                type="button"
                                onClick={(event) => { event.stopPropagation(); if (!used) onDeleteAsset(asset); }}
                                disabled={used}
                                title={used ? "Remove its timeline clips before deleting this asset" : "Delete asset"}
                                className="absolute bottom-1 right-1 rounded bg-black/60 p-1 text-[#b6b1aa] opacity-0 transition-opacity hover:text-destructive disabled:cursor-not-allowed disabled:opacity-30 group-hover:opacity-100"
                            >
                                <Trash2 className="h-3 w-3" />
                            </button>
                        </div>
                    );
                })}
            </div>
        </section>
    );
}
