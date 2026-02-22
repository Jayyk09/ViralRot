import { useState, useCallback, useEffect } from "react";
import {
    SingleDialogue,
    DialogueLine,
    ImageConfig,
    ImageSize,
    ImageEditorState,
    ValidationResult,
} from "@/lib/types";
import {
    deepClone,
    isFilenameUsedInTranscript,
    getUniqueFilename,
    validateBeforeUpload,
} from "@/lib/validation";

interface UseImageEditorOptions {
    /** Auto-rename duplicate filenames instead of throwing error */
    autoRenameDuplicates?: boolean;
    /** Validate on every change */
    validateOnChange?: boolean;
}

interface UseImageEditorReturn {
    /** Current editor state */
    state: ImageEditorState;
    /** Validation result */
    validation: ValidationResult;
    /** Add an image to a specific dialogue line */
    addImageToLine: (
        lineIdx: number,
        file: File,
        x: number,
        y: number,
        width: number,
    ) => void;
    /** Update image config (x,y,width) */
    updateImageConfig: (
        lineIdx: number,
        imageIdx: number,
        updates: Partial<ImageConfig>,
    ) => void;
    /** Remove image from a line */
    removeImage: (lineIdx: number, imageIdx: number) => void;
    /** Copy image reference to another line */
    spanImageToLines: (
        fromLineIdx: number,
        toLineIdx: number,
        imageIdx: number,
    ) => void;
    /** Replace an image file (keeps filename, updates content) */
    replaceImageFile: (oldFilename: string, newFile: File) => void;
    /** Update caption text */
    updateCaption: (lineIdx: number, caption: string) => void;
    /** Get preview URL for a filename */
    getPreviewUrl: (filename: string) => string | undefined;
    /** Get all image files as array */
    getImageFiles: () => File[];
    /** Get serialized transcript for upload */
    getTranscriptJson: () => string;
    /** Check if transcript has any images */
    hasImages: () => boolean;
    /** Remove all images */
    clearAllImages: () => void;
    /** Reset to initial state */
    reset: () => void;
    /** Manually trigger validation */
    validate: () => ValidationResult;
}

/**
 * Hook for managing transcript image editing state.
 * Handles file tracking, preview URLs, validation, and state updates.
 *
 * Updated for single dialogue format (no longer multi-subtopic).
 */
export function useImageEditor(
    initialTranscript: { dialogue: SingleDialogue },
    options: UseImageEditorOptions = {},
): UseImageEditorReturn {
    const { autoRenameDuplicates = true, validateOnChange = true } = options;

    const [state, setState] = useState<ImageEditorState>(() => ({
        transcript: deepClone(initialTranscript),
        imageFiles: new Map(),
        imagePreviewUrls: new Map(),
    }));

    const [validation, setValidation] = useState<ValidationResult>({
        valid: true,
        errors: [],
        warnings: [],
    });

    // Cleanup preview URLs on unmount
    useEffect(() => {
        return () => {
            state.imagePreviewUrls.forEach((url) => {
                URL.revokeObjectURL(url);
            });
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Re-validate when state changes
    useEffect(() => {
        if (validateOnChange) {
            const result = validateBeforeUpload(
                state.transcript,
                state.imageFiles,
            );
            setValidation(result);
        }
    }, [state, validateOnChange]);

    const addImageToLine = useCallback(
        (lineIdx: number, file: File, x: number, y: number, width: number) => {
            setState((prevState) => {
                const newTranscript = deepClone(prevState.transcript);
                const newFiles = new Map(prevState.imageFiles);
                const newPreviews = new Map(prevState.imagePreviewUrls);

                let filename = file.name;

                // Handle duplicate filenames
                if (newFiles.has(filename)) {
                    const existingFile = newFiles.get(filename);
                    if (existingFile !== file) {
                        if (autoRenameDuplicates) {
                            filename = getUniqueFilename(
                                filename,
                                new Set(newFiles.keys()),
                            );
                            // Create a new File with the unique name
                            file = new File([file], filename, {
                                type: file.type,
                            });
                        } else {
                            console.error(
                                `A different file named "${filename}" already exists`,
                            );
                            return prevState;
                        }
                    }
                }

                // Update transcript (single dialogue format)
                const line = newTranscript.dialogue?.dialogue[lineIdx];
                if (!line) {
                    console.error(`Invalid line reference: line ${lineIdx}`);
                    return prevState;
                }

                (line.images ||= []).push({
                    filename,
                    x,
                    y,
                    width,
                });
                // Track file
                newFiles.set(filename, file);

                // Create preview URL
                newPreviews.set(filename, URL.createObjectURL(file));

                return {
                    ...prevState,
                    transcript: newTranscript,
                    imageFiles: newFiles,
                    imagePreviewUrls: newPreviews,
                };
            });
        },
        [autoRenameDuplicates],
    );

    const updateImageConfig = useCallback(
        (lineIdx: number, imageIdx: number, updates: Partial<ImageConfig>) => {
            setState((prevState) => {
                const newTranscript = deepClone(prevState.transcript);
                const line = newTranscript.dialogue?.dialogue[lineIdx];

                // if not line or line.images then return
                if (!line || !line.images?.[imageIdx]) return prevState;

                line.images[imageIdx] = {
                    ...line.images[imageIdx],
                    ...updates,
                };

                return {
                    ...prevState,
                    transcript: newTranscript,
                };
            });
        },
        [],
    );

    const removeImage = useCallback((lineIdx: number, imageIdx: number) => {
        setState((prevState) => {
            const newTranscript = deepClone(prevState.transcript);
            const line = newTranscript.dialogue?.dialogue[lineIdx];

            if (!line || !line.images?.[imageIdx]) return prevState;

            const filename = line.images[imageIdx].filename;
            const newImages = line.images.filter((_, idx) => idx != imageIdx);
            line.images = newImages;

            // Check if filename is still used elsewhere
            const stillUsed = isFilenameUsedInTranscript(
                newTranscript,
                filename,
            );

            // only delete the file that is not referenced by other lines
            if (!stillUsed && filename) {
                const newFiles = new Map(prevState.imageFiles);
                const newPreviews = new Map(prevState.imagePreviewUrls);

                newFiles.delete(filename);

                const previewUrl = newPreviews.get(filename);
                if (previewUrl) {
                    URL.revokeObjectURL(previewUrl);
                    newPreviews.delete(filename);
                }

                return {
                    ...prevState,
                    transcript: newTranscript,
                    imageFiles: newFiles,
                    imagePreviewUrls: newPreviews,
                };
            }

            return { ...prevState, transcript: newTranscript };
        });
    }, []);

    const spanImageToLines = useCallback(
        (fromLineIdx: number, toLineIdx: number, imageIdx: number) => {
            setState((prevState) => {
                const newTranscript = deepClone(prevState.transcript);
                const dialogue = newTranscript.dialogue?.dialogue;
                if (!dialogue) return prevState;

                const fromLine = dialogue[fromLineIdx];
                if (!fromLine) return prevState;

                if (!fromLine?.images?.[imageIdx]) {
                        console.error(`No image at ${fromLineIdx} line image index ${imageIdx}`);
                        return prevState;
                }

                const imageConfig = fromLine?.images?.[imageIdx];
                if (!imageConfig) {
                    console.error(`Source line has no image`);
                    return prevState;
                }

                // filter out filename form subsequent images to clean up
                for(let i = fromLineIdx; i <= dialogue.length; i++) {
                        const line = dialogue[i];
                        line.images?.filter(( image => {
                                image.filename != imageConfig.filename;
                        }))
                }

                // copy image fromLineIdx to toLineIdx images array by destructuring it
                for(let i = fromLineIdx + 1; i <= toLineIdx; i++) {
                        // get line and then get the images
                        const line = dialogue[i];
                        (line.images || []).push({...imageConfig});
                }
                const toLine = newTranscript.dialogue?.dialogue[toLineIdx];

                if (!toLine.images) {
                    console.error(`Invalid target line: ${toLineIdx}`);
                    return prevState;
                }

                (toLine.images || []).push(fromLine.images[imageIdx]);

                return {
                    ...prevState,
                    transcript: newTranscript,
                };
            });
        },
        [],
    );

    const replaceImageFile = useCallback(
        (oldFilename: string, newFile: File) => {
            setState((prevState) => {
                if (!prevState.imageFiles.has(oldFilename)) {
                    console.error(`File "${oldFilename}" not found`);
                    return prevState;
                }

                // Create new File with old filename
                const renamedFile = new File([newFile], oldFilename, {
                    type: newFile.type,
                });

                const newFiles = new Map(prevState.imageFiles);
                newFiles.set(oldFilename, renamedFile);

                const newPreviews = new Map(prevState.imagePreviewUrls);
                const oldUrl = newPreviews.get(oldFilename);
                if (oldUrl) URL.revokeObjectURL(oldUrl);
                newPreviews.set(oldFilename, URL.createObjectURL(renamedFile));

                return {
                    ...prevState,
                    imageFiles: newFiles,
                    imagePreviewUrls: newPreviews,
                };
            });
        },
        [],
    );

    const updateCaption = useCallback((lineIdx: number, caption: string) => {
        setState((prevState) => {
            const newTranscript = deepClone(prevState.transcript);
            const line = newTranscript.dialogue?.dialogue[lineIdx];

            if (!line) {
                console.error(`Invalid line: ${lineIdx}`);
                return prevState;
            }

            line.caption = caption;

            return {
                ...prevState,
                transcript: newTranscript,
            };
        });
    }, []);

    const getPreviewUrl = useCallback(
        (filename: string): string | undefined => {
            return state.imagePreviewUrls.get(filename);
        },
        [state.imagePreviewUrls],
    );

    const getImageFiles = useCallback((): File[] => {
        return Array.from(state.imageFiles.values());
    }, [state.imageFiles]);

    const getTranscriptJson = useCallback((): string => {
        return JSON.stringify({ dialogue: state.transcript.dialogue });
    }, [state.transcript]);

    const hasImages = useCallback((): boolean => {
        return state.imageFiles.size > 0;
    }, [state.imageFiles]);

    const clearAllImages = useCallback(() => {
        setState((prevState) => {
            const newTranscript = deepClone(prevState.transcript);

            // Remove all image references (single dialogue format)
            newTranscript.dialogue?.dialogue.forEach((line) => {
                delete line.images;
            });

            // Revoke all preview URLs
            prevState.imagePreviewUrls.forEach((url) => {
                URL.revokeObjectURL(url);
            });

            return {
                ...prevState,
                transcript: newTranscript,
                imageFiles: new Map(),
                imagePreviewUrls: new Map(),
            };
        });
    }, []);

    const reset = useCallback(() => {
        setState((prevState) => {
            // Revoke all preview URLs
            prevState.imagePreviewUrls.forEach((url) => {
                URL.revokeObjectURL(url);
            });

            return {
                transcript: deepClone(initialTranscript),
                imageFiles: new Map(),
                imagePreviewUrls: new Map(),
            };
        });
    }, [initialTranscript]);

    const validate = useCallback((): ValidationResult => {
        const result = validateBeforeUpload(state.transcript, state.imageFiles);
        setValidation(result);
        return result;
    }, [state]);

    return {
        state,
        validation,
        addImageToLine,
        updateImageConfig,
        removeImage,
        spanImageToLines,
        replaceImageFile,
        updateCaption,
        getPreviewUrl,
        getImageFiles,
        getTranscriptJson,
        hasImages,
        clearAllImages,
        reset,
        validate,
    };
}
