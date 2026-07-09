"use client";

import React, { useState } from "react";
import { useQuery, useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
    Video as VideoIcon,
    Loader2,
    ArrowLeft,
    PlayCircle,
} from "lucide-react";
import { TopNav } from "@/components/TopNavBar";
import {
    fetchCollections,
    fetchCollectionDetails,
    CollectionSummary,
    CollectionDetails,
} from "@/lib/api";

export default function ExplorePage() {
    const {
        data: collectionsData,
        error,
        status,
    } = useQuery({
        queryKey: ["collections"],
        queryFn: () => fetchCollections(),
    });

    const collections = collectionsData?.collections ?? [];

    // Fetch details for each collection to get video thumbnails
    const collectionDetailsQueries = useQueries({
        queries: collections.map((collection) => ({
            queryKey: ["collection", collection.id],
            queryFn: () => fetchCollectionDetails(collection.id),
            enabled: collections.length > 0,
        })),
    });

    // Combine collection summaries with their details
    const collectionsWithDetails = collections.map((collection, index) => ({
        ...collection,
        details: collectionDetailsQueries[index]?.data as
            | CollectionDetails
            | undefined,
        isLoading: collectionDetailsQueries[index]?.isLoading,
    }));

    return (
        <div className="min-h-screen bg-background">
            <TopNav variant="app" />

            <div className="container mx-auto px-4 pt-20 pb-12">
                {/* Header */}
                <div className="mb-10">
                    <Link href="/feed">
                        <Button variant="ghost" size="sm" className="mb-6 -ml-2">
                            <ArrowLeft className="h-4 w-4 mr-2" />
                            Back to Feed
                        </Button>
                    </Link>
                    <div className="space-y-2">
                        <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-foreground">
                            Explore Collections
                        </h1>
                        <p className="text-muted-foreground text-lg">
                            Discover educational content across all subjects
                        </p>
                    </div>
                </div>

                {/* Loading State */}
                {status === "pending" && (
                    <div className="flex items-center justify-center py-20">
                        <div className="text-center">
                            <Loader2 className="h-12 w-12 text-primary animate-spin mx-auto mb-4" />
                            <p className="text-foreground text-lg">
                                Loading collections...
                            </p>
                        </div>
                    </div>
                )}

                {/* Error State */}
                {status === "error" && (
                    <div className="flex items-center justify-center py-20">
                        <div className="text-center">
                            <VideoIcon className="h-16 w-16 text-destructive mx-auto mb-4" />
                            <h3 className="text-xl font-semibold text-foreground mb-2">
                                Failed to load collections
                            </h3>
                            <p className="text-muted-foreground mb-6">
                                {(error as Error)?.message ?? "Unknown error"}
                            </p>
                            <Button onClick={() => window.location.reload()}>
                                Try Again
                            </Button>
                        </div>
                    </div>
                )}

                {/* Collections Grid - Instagram Explore Style */}
                {status === "success" && collections.length > 0 && (
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                        {collectionsWithDetails.map((collection) => {
                            const firstVideo = collection.details?.videos?.[0];
                            const videoCount =
                                collection.details?.video_count || 0;

                            return (
                                <Link
                                    key={collection.id}
                                    href={`/feed?collection=${collection.id}`}
                                    className="group"
                                >
                                    <div className="relative aspect-[3/4] bg-card rounded-lg overflow-hidden border border-border transition-all duration-200 hover:border-primary/50">
                                        {/* Video Thumbnail Background */}
                                        {firstVideo?.presigned_url ? (
                                            <>
                                                <video
                                                    src={
                                                        firstVideo.presigned_url
                                                    }
                                                    className="absolute inset-0 w-full h-full object-cover"
                                                    muted
                                                    playsInline
                                                    preload="metadata"
                                                />
                                                {/* Dark overlay for readability */}
                                                <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-background/10" />
                                            </>
                                        ) : (
                                            <>
                                                {/* Fallback fill */}
                                                <div className="absolute inset-0 bg-primary/10" />
                                                <div className="absolute inset-0 flex items-center justify-center">
                                                    <VideoIcon className="h-16 w-16 text-foreground/20" />
                                                </div>
                                            </>
                                        )}

                                        {/* Video Count Badge */}
                                        {videoCount > 0 && (
                                            <div className="absolute top-3 right-3 bg-background/80 backdrop-blur-sm px-3 py-1 rounded-full flex items-center gap-1.5">
                                                <PlayCircle className="h-3.5 w-3.5 text-foreground" />
                                                <span className="text-xs font-semibold text-foreground">
                                                    {videoCount}
                                                </span>
                                            </div>
                                        )}

                                        {/* Content Overlay */}
                                        <div className="absolute inset-0 flex flex-col justify-end p-4">
                                            <div className="transform transition-transform duration-300 group-hover:translate-y-0 translate-y-1">
                                                <h3 className="text-foreground font-semibold text-base md:text-lg line-clamp-2 mb-1">
                                                    {collection.title}
                                                </h3>
                                                {videoCount > 0 && (
                                                    <p className="text-muted-foreground text-xs md:text-sm">
                                                        {videoCount}{" "}
                                                        {videoCount === 1
                                                            ? "video"
                                                            : "videos"}
                                                    </p>
                                                )}
                                            </div>
                                        </div>

                                        {/* Play Icon on Hover */}
                                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                                            <div className="bg-primary rounded-full p-4 transform scale-90 group-hover:scale-100 transition-transform duration-200">
                                                <PlayCircle className="h-10 w-10 text-primary-foreground" />
                                            </div>
                                        </div>

                                        {/* Loading State */}
                                        {collection.isLoading && (
                                            <div className="absolute inset-0 flex items-center justify-center bg-background/50">
                                                <Loader2 className="h-8 w-8 text-foreground animate-spin" />
                                            </div>
                                        )}
                                    </div>
                                </Link>
                            );
                        })}
                    </div>
                )}

                {/* Empty State */}
                {status === "success" && collections.length === 0 && (
                    <div className="flex items-center justify-center py-32">
                        <div className="text-center max-w-md">
                            <div className="relative inline-block mb-6">
                                <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full" />
                                <div className="relative bg-card border border-border p-6 rounded-full">
                                    <VideoIcon className="h-16 w-16 text-primary" />
                                </div>
                            </div>
                            <h3 className="text-2xl font-semibold text-foreground mb-3">
                                No collections yet
                            </h3>
                            <p className="text-muted-foreground text-lg mb-8">
                                Collections will appear here once they&apos;re
                                created. Start creating educational content.
                            </p>
                            <Link href="/feed">
                                <Button>Go to Feed</Button>
                            </Link>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
