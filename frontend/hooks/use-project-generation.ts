import { useCallback, useEffect, useRef, useState } from "react";
import { ProgressUpdate, ProjectCreateRequest, isProjectGenerationResult } from "@/lib/types";
import { JobProgressManager, pollJobProgress } from "@/lib/websocket";
import { createEditorProject } from "@/lib/api";

interface UseJobProgressOptions {
    usePolling?: boolean;
    pollingInterval?: number;
    userId?: number;
}

export function useJobProgress(
    jobId: string | null,
    options: UseJobProgressOptions = {},
) {
    const { usePolling = false, pollingInterval = 2000, userId = 1 } = options;
    const [progress, setProgress] = useState<ProgressUpdate | null>(null);
    const [error, setError] = useState<Error | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const managerRef = useRef<JobProgressManager | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const disconnect = useCallback(() => {
        managerRef.current?.disconnect();
        managerRef.current = null;
        abortControllerRef.current?.abort();
        abortControllerRef.current = null;
        setIsConnected(false);
    }, []);

    useEffect(() => {
        if (!jobId) {
            setProgress(null);
            setError(null);
            setIsConnected(false);
            return;
        }
        setError(null);
        if (usePolling) {
            abortControllerRef.current = new AbortController();
            setIsConnected(true);
            void pollJobProgress(jobId, userId, setProgress, {
                interval: pollingInterval,
                onError: (reason) => {
                    setError(reason);
                    setIsConnected(false);
                },
            });
            return () => abortControllerRef.current?.abort();
        }

        managerRef.current = new JobProgressManager();
        managerRef.current.connect(jobId, {
            onProgress: setProgress,
            onError: setError,
            onConnect: () => setIsConnected(true),
            onDisconnect: () => setIsConnected(false),
        });
        return () => managerRef.current?.disconnect();
    }, [jobId, pollingInterval, usePolling, userId]);

    const isComplete = progress?.type === "completed";
    const isFailed = progress?.type === "error" || progress?.status === "failed";
    return {
        progress,
        error,
        isConnected,
        isLoading: Boolean(jobId) && !isComplete && !isFailed,
        isComplete,
        isFailed,
        disconnect,
    };
}

export function useProjectGeneration(userId: number = 1) {
    const [jobId, setJobId] = useState<string | null>(null);
    const [apiError, setApiError] = useState<Error | null>(null);
    const job = useJobProgress(jobId, { userId });

    const generate = useCallback(async (
        request: Omit<ProjectCreateRequest, "user_id">,
    ) => {
        setApiError(null);
        setJobId(null);
        try {
            const created = await createEditorProject({ ...request, user_id: userId });
            setJobId(created.job_id);
        } catch (reason) {
            const error = reason instanceof Error ? reason : new Error("Failed to create project");
            setApiError(error);
            throw error;
        }
    }, [userId]);

    const projectId = job.isComplete && isProjectGenerationResult(job.progress?.result)
        ? job.progress.result.project_id
        : null;

    return {
        ...job,
        jobId,
        projectId,
        error: apiError ?? job.error,
        generate,
        reset: () => {
            setJobId(null);
            setApiError(null);
        },
    };
}
