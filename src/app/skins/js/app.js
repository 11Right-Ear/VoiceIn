/**
 * VoiceIn Skin Maker - Main Application
 * Frame animation editor for creating VoiceIn tray icons
 */

import skinExporter from './skin-exporter.js';
import CanvasEditor from './canvas-editor.js';
import AnimationPreview from './animation-preview.js';

class SkinMakerApp {
    constructor() {
        // State management
        this.skinData = {
            meta: {
                name: 'VoiceIn Skin',
                author: '',
                version: '1.0'
            },
            frameSize: {
                width: 64,
                height: 64
            },
            states: {
                idle: { frames: [], loop: true, interval: 100 },
                recording: { frames: [], loop: true, interval: 100 },
                recognizing: { frames: [], loop: true, interval: 100 },
                completed: { frames: [], loop: true, interval: 100 },
                error: { frames: [], loop: true, interval: 100 },
                drag: { frames: [], loop: true, interval: 100 }
            }
        };

        this.currentState = 'idle';
        this.clipboard = null;

        // Initialize components
        this.initEditor();
        this.initPreview();
        this.initEventListeners();
        this.initDragDrop();
        this.loadFromLocalStorage();
        this.updateUI();
    }

    /**
     * Initialize canvas editor
     */
    initEditor() {
        this.editor = new CanvasEditor('editor-canvas', {
            frameWidth: this.skinData.frameSize.width,
            frameHeight: this.skinData.frameSize.height
        });
    }

    /**
     * Initialize animation preview
     */
    initPreview() {
        this.preview = new AnimationPreview('preview-canvas', {
            frameWidth: this.skinData.frameSize.width,
            frameHeight: this.skinData.frameSize.height,
            scale: 4,
            fps: 10
        });

        // Fullscreen preview
        this.fullscreenPreview = new AnimationPreview('fullscreen-canvas', {
            frameWidth: this.skinData.frameSize.width,
            frameHeight: this.skinData.frameSize.height,
            scale: Math.min(
                Math.floor(window.innerWidth / this.skinData.frameSize.width),
                Math.floor(window.innerHeight / this.skinData.frameSize.height),
                8
            ),
            fps: 10
        });
    }

    /**
     * Initialize all event listeners
     */
    initEventListeners() {
        // File input for adding frames
        document.getElementById('btn-add-frames').addEventListener('click', () => {
            document.getElementById('file-input').click();
        });

        document.getElementById('file-input').addEventListener('change', (e) => {
            this.handleFilesAdded(e.target.files);
            e.target.value = '';
        });

        // Frame operations
        document.getElementById('btn-delete-frame').addEventListener('click', () => {
            this.deleteSelectedFrame();
        });

        document.getElementById('btn-copy-frame').addEventListener('click', () => {
            this.copySelectedFrame();
        });

        // Frame navigation
        document.getElementById('btn-prev-frame').addEventListener('click', () => {
            this.prevFrame();
        });

        document.getElementById('btn-next-frame').addEventListener('click', () => {
            this.nextFrame();
        });

        // Ghost (onion skin) toggle
        document.getElementById('show-ghost').addEventListener('change', (e) => {
            this.toggleGhost(e.target.checked);
        });

        // State selection
        document.querySelectorAll('input[name="state"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.switchState(e.target.value);
            });
        });

        // State options
        document.getElementById('state-loop').addEventListener('change', (e) => {
            this.skinData.states[this.currentState].loop = e.target.checked;
        });

        document.getElementById('state-interval').addEventListener('input', (e) => {
            this.skinData.states[this.currentState].interval = parseInt(e.target.value) || 100;
        });

        // Preview controls
        document.getElementById('btn-play-preview').addEventListener('click', () => {
            this.preview.play();
        });

        document.getElementById('btn-stop-preview').addEventListener('click', () => {
            this.preview.stop();
        });

        document.getElementById('preview-fps').addEventListener('input', (e) => {
            const fps = parseInt(e.target.value);
            this.preview.setFps(fps);
            document.getElementById('preview-fps-value').textContent = fps;
        });

        // Fullscreen preview
        document.getElementById('btn-fullscreen').addEventListener('click', () => {
            this.openFullscreenModal();
        });

        document.getElementById('modal-close').addEventListener('click', () => {
            this.closeFullscreenModal();
        });

        document.getElementById('btn-play-fullscreen').addEventListener('click', () => {
            this.fullscreenPreview.play();
        });

        document.getElementById('btn-stop-fullscreen').addEventListener('click', () => {
            this.fullscreenPreview.stop();
        });

        // Export
        document.getElementById('btn-export').addEventListener('click', () => {
            this.openExportModal();
        });

        document.getElementById('btn-download-zip').addEventListener('click', () => {
            this.downloadSkinZip();
        });

        document.getElementById('btn-copy-export-json').addEventListener('click', () => {
            this.copyExportJson();
        });

        document.getElementById('export-modal-close').addEventListener('click', () => {
            this.closeExportModal();
        });

        // Preview all states
        document.getElementById('btn-preview-all').addEventListener('click', () => {
            this.previewAllStates();
        });

        // Skin metadata
        document.getElementById('skin-name').addEventListener('input', (e) => {
            this.skinData.meta.name = e.target.value;
        });

        document.getElementById('skin-author').addEventListener('input', (e) => {
            this.skinData.meta.author = e.target.value;
        });

        document.getElementById('skin-version').addEventListener('input', (e) => {
            this.skinData.meta.version = e.target.value;
        });

        // Frame size
        document.getElementById('frame-width').addEventListener('change', (e) => {
            this.skinData.frameSize.width = parseInt(e.target.value) || 64;
            this.updateFrameSize();
        });

        document.getElementById('frame-height').addEventListener('change', (e) => {
            this.skinData.frameSize.height = parseInt(e.target.value) || 64;
            this.updateFrameSize();
        });

        // Save/Load
        document.getElementById('btn-copy-json').addEventListener('click', () => {
            this.copySkinJson();
        });

        document.getElementById('btn-save-local').addEventListener('click', () => {
            this.saveToLocalStorage();
        });

        document.getElementById('btn-load-local').addEventListener('click', () => {
            this.loadFromLocalStorage();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 'c':
                        if (document.activeElement.tagName !== 'INPUT') {
                            this.copySelectedFrame();
                            e.preventDefault();
                        }
                        break;
                    case 'v':
                        if (document.activeElement.tagName !== 'INPUT') {
                            this.pasteFrame();
                            e.preventDefault();
                        }
                        break;
                    case 'Delete':
                        if (document.activeElement.tagName !== 'INPUT') {
                            this.deleteSelectedFrame();
                            e.preventDefault();
                        }
                        break;
                }
            }
        });
    }

    /**
     * Initialize drag and drop
     */
    initDragDrop() {
        const editorEl = document.getElementById('canvas-editor');
        const overlay = document.getElementById('canvas-overlay');

        editorEl.addEventListener('dragover', (e) => {
            e.preventDefault();
            editorEl.classList.add('drag-over');
        });

        editorEl.addEventListener('dragleave', () => {
            editorEl.classList.remove('drag-over');
        });

        editorEl.addEventListener('drop', (e) => {
            e.preventDefault();
            editorEl.classList.remove('drag-over');
            this.handleFilesAdded(e.dataTransfer.files);
        });
    }

    /**
     * Handle files added
     * @param {FileList} files
     */
    async handleFilesAdded(files) {
        if (!files || files.length === 0) return;

        const added = await this.editor.addFrames(files);

        if (added > 0) {
            // Add frames to current state
            const frames = this.editor.getFrames();
            this.skinData.states[this.currentState].frames = [...frames];
            this.updatePreview();
            this.updateFrameList();
            this.updateStateCount();
            this.updateOverlay();
        }
    }

    /**
     * Update frame list UI
     */
    updateFrameList() {
        const container = document.getElementById('frame-list');
        const frames = this.skinData.states[this.currentState].frames;

        container.innerHTML = '';

        frames.forEach((frame, index) => {
            const item = document.createElement('div');
            item.className = 'frame-item';
            if (index === this.editor.selectedIndex) {
                item.classList.add('frame-item--selected');
            }

            item.innerHTML = `
                <img class="frame-item__thumbnail" src="${frame.imageData}" alt="Frame ${index + 1}">
                <div class="frame-item__info">
                    <div class="frame-item__index">帧 ${index + 1}</div>
                    <div class="frame-item__duration">${frame.duration}ms</div>
                </div>
            `;

            item.addEventListener('click', () => {
                this.selectFrame(index);
            });

            container.appendChild(item);
        });
    }

    /**
     * Select frame by index
     * @param {number} index
     */
    selectFrame(index) {
        this.editor.selectFrame(index);
        this.updateFrameList();
        this.updateFrameIndicator();
    }

    /**
     * Delete selected frame
     */
    deleteSelectedFrame() {
        if (this.editor.deleteSelected()) {
            this.skinData.states[this.currentState].frames = this.editor.getFrames();
            this.updateFrameList();
            this.updateStateCount();
            this.updatePreview();
            this.updateOverlay();
        }
    }

    /**
     * Copy selected frame
     */
    copySelectedFrame() {
        this.clipboard = this.editor.copySelected();
    }

    /**
     * Paste frame
     */
    pasteFrame() {
        if (this.clipboard) {
            this.editor.pasteAfter(this.clipboard);
            this.skinData.states[this.currentState].frames = this.editor.getFrames();
            this.updateFrameList();
            this.updateStateCount();
            this.updatePreview();
            this.updateOverlay();
        }
    }

    /**
     * Previous frame
     */
    prevFrame() {
        const newIndex = Math.max(0, this.editor.selectedIndex - 1);
        this.selectFrame(newIndex);
    }

    /**
     * Next frame
     */
    nextFrame() {
        const newIndex = Math.min(this.editor.getFrames().length - 1, this.editor.selectedIndex + 1);
        this.selectFrame(newIndex);
    }

    /**
     * Toggle ghost/onion skin
     * @param {boolean} show
     */
    toggleGhost(show) {
        const frames = this.editor.getFrames();
        const currentIdx = this.editor.selectedIndex;
        let ghostIdx = -1;

        if (show && frames.length > 1) {
            ghostIdx = currentIdx > 0 ? currentIdx - 1 : frames.length - 1;
        }

        this.editor.setGhost(show, ghostIdx);
    }

    /**
     * Switch to different state
     * @param {string} stateName
     */
    switchState(stateName) {
        this.currentState = stateName;

        // Save current editor frames first
        this.skinData.states[this.currentState].frames = this.editor.getFrames();

        // Load frames for new state
        const newFrames = this.skinData.states[stateName].frames;
        this.editor.setFrames(newFrames);

        // Update UI
        this.updateFrameList();
        this.updateStateOptions();
        this.updatePreview();
        this.updateOverlay();

        // Update preview
        this.preview.setCurrentState(stateName);
    }

    /**
     * Update state options UI
     */
    updateStateOptions() {
        const state = this.skinData.states[this.currentState];
        document.getElementById('state-loop').checked = state.loop;
        document.getElementById('state-interval').value = state.interval;
    }

    /**
     * Update preview
     */
    updatePreview() {
        const state = this.skinData.states[this.currentState];
        this.preview.setStateFrames(this.currentState, state.frames, {
            loop: state.loop,
            interval: state.interval
        });
        this.fullscreenPreview.setStateFrames(this.currentState, state.frames, {
            loop: state.loop,
            interval: state.interval
        });

        // Update all states in preview
        for (const [stateName, stateData] of Object.entries(this.skinData.states)) {
            this.preview.setStateFrames(stateName, stateData.frames, {
                loop: stateData.loop,
                interval: stateData.interval
            });
            this.fullscreenPreview.setStateFrames(stateName, stateData.frames, {
                loop: stateData.loop,
                interval: stateData.interval
            });
        }

        this.preview.render();
    }

    /**
     * Update state frame count display
     */
    updateStateCount() {
        for (const [stateName, stateData] of Object.entries(this.skinData.states)) {
            const countEl = document.getElementById(`state-count-${stateName}`);
            if (countEl) {
                countEl.textContent = `${stateData.frames.length}帧`;
            }
        }
    }

    /**
     * Update frame indicator
     */
    updateFrameIndicator() {
        const frames = this.editor.getFrames();
        const idx = this.editor.selectedIndex;
        document.getElementById('frame-indicator').textContent =
            `第 ${idx + 1} / ${frames.length} 帧`;
    }

    /**
     * Update canvas overlay visibility
     */
    updateOverlay() {
        const overlay = document.getElementById('canvas-overlay');
        const hasFrames = this.editor.getFrames().length > 0;
        overlay.classList.toggle('canvas-overlay--hidden', hasFrames);
    }

    /**
     * Update frame size
     */
    updateFrameSize() {
        const { width, height } = this.skinData.frameSize;
        this.editor.setFrameSize(width, height);
        this.preview.setFrameSize(width, height);
        this.fullscreenPreview.setFrameSize(width, height);
        this.updatePreview();
    }

    /**
     * Open fullscreen modal
     */
    openFullscreenModal() {
        document.getElementById('fullscreen-modal').classList.add('modal--active');
        document.getElementById('fullscreen-state').textContent = this.currentState;
        this.fullscreenPreview.setCurrentState(this.currentState);
        this.fullscreenPreview.render();
    }

    /**
     * Close fullscreen modal
     */
    closeFullscreenModal() {
        document.getElementById('fullscreen-modal').classList.remove('modal--active');
        this.fullscreenPreview.stop();
    }

    /**
     * Preview all states
     */
    previewAllStates() {
        // First sync all states
        this.updatePreview();
        this.preview.previewAllStates();
    }

    /**
     * Open export modal
     */
    openExportModal() {
        document.getElementById('export-modal').classList.add('modal--active');

        // Update export info
        document.getElementById('export-name').textContent = this.skinData.meta.name;
        document.getElementById('export-size').textContent =
            `${this.skinData.frameSize.width}×${this.skinData.frameSize.height}`;

        let totalFrames = 0;
        for (const state of Object.values(this.skinData.states)) {
            totalFrames += state.frames.length;
        }
        document.getElementById('export-frame-count').textContent = totalFrames;

        // Draw preview in export modal
        const previewCanvas = document.getElementById('export-preview-canvas');
        const previewCtx = previewCanvas.getContext('2d');
        previewCanvas.width = this.skinData.frameSize.width * 2;
        previewCanvas.height = this.skinData.frameSize.height * 2;
        previewCtx.imageSmoothingEnabled = false;

        // Draw checkerboard
        const size = 8;
        for (let y = 0; y < previewCanvas.height; y += size) {
            for (let x = 0; x < previewCanvas.width; x += size) {
                const isLight = ((x / size) + (y / size)) % 2 === 0;
                previewCtx.fillStyle = isLight ? '#2a2a4a' : '#1a1a2e';
                previewCtx.fillRect(x, y, size, size);
            }
        }

        // Draw first frame of idle state
        const idleFrames = this.skinData.states.idle.frames;
        if (idleFrames.length > 0 && idleFrames[0].imageData) {
            const img = new Image();
            img.onload = () => {
                previewCtx.drawImage(img, 0, 0, previewCanvas.width, previewCanvas.height);
            };
            img.src = idleFrames[0].imageData;
        }
    }

    /**
     * Close export modal
     */
    closeExportModal() {
        document.getElementById('export-modal').classList.remove('modal--active');
    }

    /**
     * Download skin as ZIP
     */
    async downloadSkinZip() {
        // Sync current state frames first
        this.skinData.states[this.currentState].frames = this.editor.getFrames();

        const validation = skinExporter.validate(this.skinData);
        if (!validation.valid) {
            alert('导出失败:\n' + validation.errors.join('\n'));
            return;
        }

        try {
            const zipBlob = await skinExporter.exportAsZip(this.skinData);
            const fileName = `${this.skinData.meta.name.replace(/[^a-zA-Z0-9一-龥]/g, '_')}.zip`;
            skinExporter.downloadZip(zipBlob, fileName);
            this.closeExportModal();
        } catch (error) {
            console.error('Export error:', error);
            alert('导出失败: ' + error.message);
        }
    }

    /**
     * Copy export JSON
     */
    copyExportJson() {
        this.skinData.states[this.currentState].frames = this.editor.getFrames();
        const json = skinExporter.getConfigJson(this.skinData);
        navigator.clipboard.writeText(json).then(() => {
            alert('JSON 已复制到剪贴板');
        }).catch(err => {
            console.error('Copy failed:', err);
            alert('复制失败');
        });
    }

    /**
     * Copy skin JSON
     */
    copySkinJson() {
        this.skinData.states[this.currentState].frames = this.editor.getFrames();
        const json = JSON.stringify(this.skinData, null, 2);
        navigator.clipboard.writeText(json).then(() => {
            alert('JSON 已复制到剪贴板');
        }).catch(err => {
            console.error('Copy failed:', err);
            alert('复制失败');
        });
    }

    /**
     * Save to localStorage
     */
    saveToLocalStorage() {
        this.skinData.states[this.currentState].frames = this.editor.getFrames();

        // Convert frames to JSON-serializable format (just imageData URLs)
        const saveData = {
            ...this.skinData,
            version: '1.0'
        };

        try {
            localStorage.setItem('voicein-skin-maker', JSON.stringify(saveData));
            alert('进度已保存');
        } catch (error) {
            console.error('Save failed:', error);
            alert('保存失败: ' + error.message);
        }
    }

    /**
     * Load from localStorage
     */
    loadFromLocalStorage() {
        try {
            const saved = localStorage.getItem('voicein-skin-maker');
            if (saved) {
                const data = JSON.parse(saved);

                // Validate data structure
                if (typeof data !== 'object' || data === null) {
                    throw new Error('Invalid data format');
                }

                // Restore metadata
                if (data.meta && typeof data.meta === 'object') {
                    this.skinData.meta = { ...this.skinData.meta, ...data.meta };
                    document.getElementById('skin-name').value = this.skinData.meta.name;
                    document.getElementById('skin-author').value = this.skinData.meta.author || '';
                    document.getElementById('skin-version').value = this.skinData.meta.version || '1.0';
                }

                // Restore frame size
                if (data.frameSize && typeof data.frameSize === 'object') {
                    const w = parseInt(data.frameSize.width);
                    const h = parseInt(data.frameSize.height);
                    if (!isNaN(w) && !isNaN(h) && w > 0 && h > 0 && w <= 2048 && h <= 2048) {
                        this.skinData.frameSize = { width: w, height: h };
                        document.getElementById('frame-width').value = this.skinData.frameSize.width;
                        document.getElementById('frame-height').value = this.skinData.frameSize.height;
                        this.updateFrameSize();
                    }
                }

                // Restore states
                if (data.states && typeof data.states === 'object') {
                    for (const [stateName, stateData] of Object.entries(data.states)) {
                        if (this.skinData.states[stateName] && typeof stateData === 'object') {
                            this.skinData.states[stateName] = {
                                ...this.skinData.states[stateName],
                                ...stateData
                            };
                        }
                    }
                }

                // Switch to current state to load its frames
                this.switchState(this.currentState);
                this.updateStateCount();
                this.updateStateOptions();
                this.updateUI();

                alert('进度已加载');
            }
        } catch (error) {
            console.error('Load failed:', error);
            alert('加载失败: ' + error.message);
        }
    }

    /**
     * Update UI elements
     */
    updateUI() {
        this.updateFrameList();
        this.updateStateCount();
        this.updateStateOptions();
        this.updatePreview();
        this.updateOverlay();
        this.updateFrameIndicator();
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.skinMakerApp = new SkinMakerApp();
});

export default SkinMakerApp;
