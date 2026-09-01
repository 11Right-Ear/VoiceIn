/**
 * Canvas Editor Module
 * Handles frame editing, dragging, and canvas rendering
 */

class CanvasEditor {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.options = {
            frameWidth: 64,
            frameHeight: 64,
            showGrid: true,
            ...options
        };

        this.frames = [];
        this.selectedIndex = -1;
        this.ghostIndex = -1;
        this.showGhost = false;
        this.isDragging = false;
        this.dragItem = null;

        this.init();
    }

    init() {
        this.canvas.width = this.options.frameWidth * 4;
        this.canvas.height = this.options.frameHeight * 4;
        this.ctx.imageSmoothingEnabled = false;
        this.drawCheckerboard();
    }

    /**
     * Set frame size
     * @param {number} width
     * @param {number} height
     */
    setFrameSize(width, height) {
        this.options.frameWidth = width;
        this.options.frameHeight = height;
        this.canvas.width = width * 4;
        this.canvas.height = height * 4;
        this.ctx.imageSmoothingEnabled = false;
        this.render();
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
     * Render current frame on canvas
     */
    render() {
        this.drawCheckerboard();

        if (this.selectedIndex >= 0 && this.selectedIndex < this.frames.length) {
            const frame = this.frames[this.selectedIndex];
            if (frame && frame.imageData) {
                this.drawFrame(frame.imageData);
            }
        }

        if (this.showGhost && this.ghostIndex >= 0 && this.ghostIndex !== this.selectedIndex) {
            this.ctx.globalAlpha = 0.3;
            if (this.ghostIndex >= 0 && this.ghostIndex < this.frames.length) {
                const ghostFrame = this.frames[this.ghostIndex];
                if (ghostFrame && ghostFrame.imageData) {
                    this.drawFrame(ghostFrame.imageData);
                }
            }
            this.ctx.globalAlpha = 1.0;
        }
    }

    /**
     * Draw frame image data on canvas
     * @param {string} imageData - Base64 or data URL
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
     * Add frames from file list
     * @param {FileList} files - List of image files
     * @returns {Promise<number>} Number of frames added
     */
    async addFrames(files) {
        let added = 0;

        for (const file of files) {
            if (file.type === 'image/png') {
                const imageData = await this.readFileAsDataURL(file);
                this.frames.push({
                    imageData,
                    duration: 100,
                    width: this.options.frameWidth,
                    height: this.options.frameHeight
                });
                added++;
            }
        }

        if (this.selectedIndex < 0 && this.frames.length > 0) {
            this.selectedIndex = 0;
        }

        this.render();
        return added;
    }

    /**
     * Read file as data URL
     * @param {File} file
     * @returns {Promise<string>}
     */
    readFileAsDataURL(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    /**
     * Select frame by index
     * @param {number} index
     */
    selectFrame(index) {
        if (index >= 0 && index < this.frames.length) {
            this.selectedIndex = index;
            this.render();
        }
    }

    /**
     * Delete selected frame
     * @returns {boolean} True if deleted
     */
    deleteSelected() {
        if (this.selectedIndex >= 0 && this.selectedIndex < this.frames.length) {
            this.frames.splice(this.selectedIndex, 1);
            if (this.selectedIndex >= this.frames.length) {
                this.selectedIndex = Math.max(0, this.frames.length - 1);
            }
            this.render();
            return true;
        }
        return false;
    }

    /**
     * Copy selected frame
     * @returns {Object|null} Copied frame data
     */
    copySelected() {
        if (this.selectedIndex >= 0 && this.selectedIndex < this.frames.length) {
            const frame = this.frames[this.selectedIndex];
            return { ...frame };
        }
        return null;
    }

    /**
     * Paste frame after selected index
     * @param {Object} frameData - Frame data to paste
     */
    pasteAfter(frameData) {
        const insertIndex = this.selectedIndex + 1;
        this.frames.splice(insertIndex, 0, { ...frameData });
        this.selectedIndex = insertIndex;
        this.render();
    }

    /**
     * Move frame from one index to another
     * @param {number} fromIndex
     * @param {number} toIndex
     */
    moveFrame(fromIndex, toIndex) {
        if (fromIndex >= 0 && fromIndex < this.frames.length &&
            toIndex >= 0 && toIndex < this.frames.length) {
            const [frame] = this.frames.splice(fromIndex, 1);
            this.frames.splice(toIndex, 0, frame);
            this.render();
        }
    }

    /**
     * Update frame duration
     * @param {number} index
     * @param {number} duration - Duration in ms
     */
    updateDuration(index, duration) {
        if (index >= 0 && index < this.frames.length) {
            this.frames[index].duration = duration;
        }
    }

    /**
     * Get all frames
     * @returns {Array}
     */
    getFrames() {
        return [...this.frames];
    }

    /**
     * Set frames (for loading state)
     * @param {Array} frames
     */
    setFrames(frames) {
        this.frames = frames;
        this.selectedIndex = frames.length > 0 ? 0 : -1;
        this.render();
    }

    /**
     * Clear all frames
     */
    clear() {
        this.frames = [];
        this.selectedIndex = -1;
        this.render();
    }

    /**
     * Toggle ghost (onion skin)
     * @param {boolean} show
     * @param {number} ghostIdx - Index of ghost frame
     */
    setGhost(show, ghostIdx = -1) {
        this.showGhost = show;
        this.ghostIndex = ghostIdx;
        this.render();
    }

    /**
     * Get current frame data
     * @returns {Object|null}
     */
    getCurrentFrame() {
        if (this.selectedIndex >= 0 && this.selectedIndex < this.frames.length) {
            return this.frames[this.selectedIndex];
        }
        return null;
    }

    /**
     * Export current canvas as PNG blob
     * @returns {Promise<Blob>}
     */
    exportCurrentAsPng() {
        return new Promise((resolve, reject) => {
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = this.options.frameWidth;
            tempCanvas.height = this.options.frameHeight;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.imageSmoothingEnabled = false;

            const img = new Image();
            img.onload = () => {
                tempCtx.drawImage(img, 0, 0, tempCanvas.width, tempCanvas.height);
                tempCanvas.toBlob((blob) => {
                    if (blob) resolve(blob);
                    else reject(new Error('Failed to create PNG blob'));
                }, 'image/png');
            };
            img.onerror = reject;

            if (this.selectedIndex >= 0 && this.frames[this.selectedIndex]) {
                img.src = this.frames[this.selectedIndex].imageData;
            } else {
                reject(new Error('No frame selected'));
            }
        });
    }
}

// ES module export
export default CanvasEditor;
export { CanvasEditor };
