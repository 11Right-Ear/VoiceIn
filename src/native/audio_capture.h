#pragma once

#ifdef AUDIO_CAPTURE_EXPORTS
#define AUDIO_API __declspec(dllexport)
#else
#define AUDIO_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Callback invoked from capture thread every block_ms milliseconds.
// samples: interleaved float32 PCM in [-1.0, 1.0]
// n_samples: total number of float values (frames * channels)
typedef void (*audio_callback_t)(const float *samples, int n_samples, int sample_rate);

// Device descriptor returned by audio_list_devices
typedef struct {
    wchar_t name[256];
    int id;                // opaque device ID for audio_init
    int max_channels;
    int default_sample_rate;
} audio_device_info_t;

// List available capture devices. Call audio_free_device_list to release.
// Returns device count, or -1 on error.
AUDIO_API int audio_list_devices(audio_device_info_t **devices_out);

AUDIO_API void audio_free_device_list(audio_device_info_t *devices);

// Initialize capture session. Does not start recording.
//   device_id:  -1 for system default, or id from audio_list_devices
//   sample_rate: typically 16000
//   channels:    1 (mono)
//   block_ms:    callback interval in milliseconds (100 recommended)
// Returns 0 on success, non-zero on error.
AUDIO_API int audio_init(int device_id, int sample_rate, int channels, int block_ms);

// Start capturing. Callback is invoked on the capture thread every block_ms.
// On error returns non-zero.
AUDIO_API int audio_start(audio_callback_t callback);

// Stop capturing, blocks until the capture thread exits.
// Remaining buffered audio is NOT delivered (caller should finalize via callback).
AUDIO_API int audio_stop(void);

// Release all WASAPI resources. Safe to call after audio_stop.
AUDIO_API void audio_close(void);

// Last error message (thread-local). Valid until next API call.
AUDIO_API const wchar_t *audio_last_error(void);

#ifdef __cplusplus
}
#endif
