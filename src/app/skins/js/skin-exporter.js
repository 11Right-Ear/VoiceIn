/**
 * Skin Exporter Module
 * Handles exporting skin packages as ZIP files with JSON config
 */

class SkinExporter {
    constructor() {
        this.zip = null;
    }

    /**
     * Sanitize string for use in filenames
     * @param {string} str - String to sanitize
     * @returns {string} Sanitized string
     */
    _sanitizeFileName(str) {
        return str.replace(/[^a-zA-Z0-9一-龥]/g, '_');
    }

    /**
     * Generate skin configuration JSON
     * @param {Object} skinData - Complete skin data
     * @returns {Object} Skin configuration object
     */
    generateConfig(skinData) {
        const { meta, frameSize, states } = skinData;

        const config = {
            name: meta.name,
            author: meta.author || 'Anonymous',
            version: meta.version || '1.0',
            frameSize: {
                width: frameSize.width,
                height: frameSize.height
            },
            states: {}
        };

        // Map state names to expected VoiceIn states
        const stateMap = {
            idle: 'idle',
            recording: 'recording',
            recognizing: 'recognizing',
            completed: 'completed',
            error: 'error',
            drag: 'drag'
        };

        for (const [stateKey, stateData] of Object.entries(states)) {
            const safeStateKey = this._sanitizeFileName(stateKey);
            const mappedState = stateMap[stateKey] || safeStateKey;
            config.states[mappedState] = {
                frames: stateData.frames.map((_, idx) => `${safeStateKey}_${idx}.png`),
                loop: stateData.loop,
                interval: stateData.interval
            };
        }

        return config;
    }

    /**
     * Export skin as ZIP file
     * @param {Object} skinData - Complete skin data with frames
     * @returns {Promise<Blob>} ZIP file blob
     */
    async exportAsZip(skinData) {
        this.zip = new JSZip();

        const config = this.generateConfig(skinData);
        this.zip.file('config.json', JSON.stringify(config, null, 2));

        // Add frames organized by state
        const framePromises = [];
        let frameIndex = 0;

        for (const [stateKey, stateData] of Object.entries(skinData.states)) {
            const safeStateKey = this._sanitizeFileName(stateKey);
            stateData.frames.forEach((frameData, idx) => {
                if (frameData && frameData.imageData) {
                    const fileName = `${safeStateKey}_${idx}.png`;
                    const promise = new Promise((resolve, reject) => {
                        const img = new Image();
                        img.onload = () => {
                            const canvas = document.createElement('canvas');
                            canvas.width = skinData.frameSize.width;
                            canvas.height = skinData.frameSize.height;
                            const ctx = canvas.getContext('2d');
                            ctx.imageSmoothingEnabled = false;
                            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                            canvas.toBlob((blob) => {
                                if (blob) {
                                    this.zip.file(fileName, blob);
                                    resolve();
                                } else {
                                    reject(new Error(`Failed to create blob for ${fileName}`));
                                }
                            }, 'image/png');
                        };
                        img.onerror = () => reject(new Error(`Failed to load image for ${fileName}`));
                        img.src = frameData.imageData;
                    });
                    framePromises.push(promise);
                }
            });
        }

        await Promise.all(framePromises);

        return await this.zip.generateAsync({ type: 'blob' });
    }

    /**
     * Download ZIP file
     * @param {Blob} zipBlob - ZIP file blob
     * @param {string} fileName - Download file name
     */
    downloadZip(zipBlob, fileName = 'skin.zip') {
        const url = URL.createObjectURL(zipBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Get JSON string of skin config (for copying)
     * @param {Object} skinData - Complete skin data
     * @returns {string} JSON string
     */
    getConfigJson(skinData) {
        return JSON.stringify(this.generateConfig(skinData), null, 2);
    }

    /**
     * Validate skin data before export
     * @param {Object} skinData - Complete skin data
     * @returns {{ valid: boolean, errors: string[] }}
     */
    validate(skinData) {
        const errors = [];

        if (!skinData.meta.name) {
            errors.push('Skin name is required');
        }

        if (!skinData.frameSize.width || !skinData.frameSize.height) {
            errors.push('Frame size must be specified');
        }

        const stateNames = Object.keys(skinData.states);
        if (stateNames.length === 0) {
            errors.push('At least one state with frames is required');
        }

        for (const [stateKey, stateData] of Object.entries(skinData.states)) {
            if (stateData.frames.length === 0) {
                errors.push(`State "${stateKey}" has no frames`);
            }
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }
}

// Export singleton instance
const skinExporter = new SkinExporter();

// ES module export
export default skinExporter;
export { SkinExporter };
