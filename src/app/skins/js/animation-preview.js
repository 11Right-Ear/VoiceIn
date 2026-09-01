/**
 * Animation Preview Module
 * Handles playback and preview of animations
 */

class AnimationPreview {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.options = {
            frameWidth: 64,
            frameHeight: 64,
            scale: 4,
            fps: 10,
            ...options
        };

        this.states = {
            idle: { frames: [], loop: true, interval: 100 },
            recording: { frames: [], loop: true, interval: 100 },
            recognizing: { frames: [], loop: true, interval: 100 },
            completed: { frames: [], loop: true, interval: 100 },
            error: { frames: [], loop: true, interval: 100 },
            drag: { frames: [], loop: true, interval: 100 }
        };

        this.currentState = 'idle';
        this.currentFrameIndex = 0;
        this.isPlaying = false;
        this.animationTimer = null;

        this.init();
    }

    init() {
        this.canvas.width = this.options.frameWidth * this.options.scale;
        this.canvas.height = this.options.frameHeight * this.options.scale;
        this.ctx.imageSmoothingEnabled = false;
    }

    /**
     * Set frame size
     * @param {number} width
     * @param {number} height
     */
    setFrameSize(width, height) {
        this.options.frameWidth = width;
        this.options.frameHeight = height;
        this.canvas.width = width * this.options.scale;
        this.canvas.height = height * this.options.scale;
        this.ctx.imageSmoothingEnabled = false;
        this.render();
    }

    /**
     * Set frames for a state
     * @param {string} stateName
     * @param {Array} frames - Array of frame objects with imageData
     * @param {Object} options - { loop, interval }
     */
    setStateFrames(stateName, frames, options = {}) {
        if (this.states[stateName]) {
            this.states[stateName].frames = frames;
            if (options.loop !== undefined) this.states[stateName].loop = options.loop;
            if (options.interval !== undefined) this.states[stateName].interval = options.interval;
        }
    }

    /**
     * Get current state data
     * @returns {Object}
     */
    getCurrentState() {
        return this.states[this.currentState];
    }

    /**
     * Set current state to preview
     * @param {string} stateName
     */
    setCurrentState(stateName) {
        if (this.states[stateName]) {
            this.currentState = stateName;
            this.currentFrameIndex = 0;
            this.render();
        }
    }

    /**
     * Set FPS for preview
     * @param {number} fps
     */
    setFps(fps) {
        this.options.fps = Math.max(10, Math.min(60, fps));
        if (this.isPlaying) {
            this.stop();
            this.play();
        }
    }

    /**
     * Render current frame
     */
    render() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw checkerboard background
        this.drawCheckerboard();

        const state = this.states[this.currentState];
        if (state && state.frames.length > 0) {
            const frame = state.frames[this.currentFrameIndex];
            if (frame && frame.imageData) {
                this.drawFrame(frame.imageData);
            }
        }
    }

    /**
     * Draw checkerboard background
     */
    drawCheckerboard() {
        const size = 8;
        const w = this.canvas.width;
        const h = this.canvas.height;

        for (let y = 0; y < h; y += size) {
            for (let x = 0; x < w; x += size) {
                const isLight = ((x / size) + (y / size)) % 2 === 0;
                this.ctx.fillStyle = isLight ? '#2a2a4a' : '#1a1a2e';
                this.ctx.fillRect(x, y, size, size);
            }
        }
    }

    /**
     * Draw frame image
     * @param {string} imageData
     */
    drawFrame(imageData) {
        const img = new Image();
        img.onload = () => {
            this.ctx.imageSmoothingEnabled = false;
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
        };
        img.src = imageData;
    }

    /**
     * Start playback
     */
    play() {
        const state = this.states[this.currentState];
        if (!state || state.frames.length === 0) return;

        this.isPlaying = true;
        this.scheduleNextFrame();
    }

    /**
     * Schedule next frame for animation
     */
    scheduleNextFrame() {
        if (!this.isPlaying) return;

        const state = this.states[this.currentState];
        const interval = state.interval || 100;

        this.animationTimer = setTimeout(() => {
            this.nextFrame();
            this.scheduleNextFrame();
        }, interval);
    }

    /**
     * Advance to next frame
     */
    nextFrame() {
        const state = this.states[this.currentState];
        if (!state || state.frames.length === 0) return;

        this.currentFrameIndex++;
        if (this.currentFrameIndex >= state.frames.length) {
            if (state.loop) {
                this.currentFrameIndex = 0;
            } else {
                this.currentFrameIndex = state.frames.length - 1;
                this.stop();
            }
        }

        this.render();
    }

    /**
     * Stop playback
     */
    stop() {
        this.isPlaying = false;
        if (this.animationTimer) {
            clearTimeout(this.animationTimer);
            this.animationTimer = null;
        }
        this.currentFrameIndex = 0;
        this.render();
    }

    /**
     * Preview all states in sequence
     */
    previewAllStates() {
        const stateNames = Object.keys(this.states);
        let idx = 0;

        const nextState = () => {
            if (idx >= stateNames.length) {
                idx = 0;
            }
            this.setCurrentState(stateNames[idx]);
            this.play();
            idx++;

            setTimeout(nextState, 2000);
        };

        nextState();
    }

    /**
     * Get animation data for export
     * @returns {Object}
     */
    getExportData() {
        return {
            states: { ...this.states },
            currentState: this.currentState
        };
    }

    /**
     * Load animation data from export
     * @param {Object} data
     */
    loadExportData(data) {
        if (data.states) {
            this.states = { ...data.states };
        }
        if (data.currentState) {
            this.currentState = data.currentState;
        }
        this.render();
    }

    /**
     * Reset all states
     */
    reset() {
        this.stop();
        for (const state of Object.values(this.states)) {
            state.frames = [];
        }
        this.render();
    }
}

// ES module export
export default AnimationPreview;
export { AnimationPreview };
