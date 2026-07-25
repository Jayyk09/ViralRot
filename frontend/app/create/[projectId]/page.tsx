"use client";

import { use, useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Editor } from "@/components/create-video/Editor";
import { fetchEditorProject } from "@/lib/api";
import { EditorProject } from "@/lib/types";

export default function PersistentEditorPage({
    params,
}: {
    params: Promise<{ projectId: string }>;
}) {
    const { projectId } = use(params);
    const [project, setProject] = useState<EditorProject | null>(null);
    const [error, setError] = useState<string | null>(null);

    const reload = useCallback(async () => {
        try {
            setError(null);
            setProject(await fetchEditorProject(projectId));
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Failed to load project");
        }
    }, [projectId]);

    useEffect(() => {
        void reload();
    }, [reload]);

    if (error) {
        return (
            <div className="flex h-screen items-center justify-center text-sm text-destructive">
                {error}
            </div>
        );
    }
    if (!project) {
        return (
            <div className="flex h-screen items-center justify-center gap-3 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading persistent editor…
            </div>
        );
    }

    return (
        <Editor
            project={project}
            onProjectChange={setProject}
            onConflict={reload}
        />
    );
}
