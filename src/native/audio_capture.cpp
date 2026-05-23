#include "audio_capture.h"
#include "ring_buffer.h"

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>

#include <cstdio>
#include <cstring>

#pragma comment(lib, "ole32.lib")

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
static constexpr size_t kRingCapacity   = 65536; // 2^16, ~256 KB
static constexpr int    kPollIntervalMs = 10;
static constexpr int    kMaxBlockFrames = 16384; // 1s at 16kHz stereo

// ---------------------------------------------------------------------------
// Per-session state
// ---------------------------------------------------------------------------
struct CaptureSession {
    int      device_id   = -1;
    int      sample_rate = 16000;
    int      channels    = 1;
    int      block_ms    = 100;

    IMMDeviceEnumerator  *enumerator     = nullptr;
    IMMDevice            *device         = nullptr;
    IAudioClient         *audio_client   = nullptr;
    IAudioCaptureClient  *capture_client = nullptr;

    WAVEFORMATEX          actual_format  = {};
    WAVEFORMATEXTENSIBLE  actual_fmt_ext = {}; // full format, may be >44 bytes
    int                   target_sample_rate = 0;
    int                   target_channels    = 0;
    bool                  need_conversion    = false;

    RingBuffer<float, kRingCapacity> *ring = nullptr;
    HANDLE                 thread       = nullptr;
    volatile LONG          running      = 0;
    audio_callback_t       callback     = nullptr;
    int                    block_samples = 0;

    CRITICAL_SECTION       error_lock;
    wchar_t                last_error[512] = {};

    CaptureSession()  { InitializeCriticalSection(&error_lock); }
    ~CaptureSession() { DeleteCriticalSection(&error_lock); }

    void set_error(const wchar_t *fmt, ...) {
        va_list args;
        va_start(args, fmt);
        EnterCriticalSection(&error_lock);
        _vsnwprintf_s(last_error, _countof(last_error), _TRUNCATE, fmt, args);
        LeaveCriticalSection(&error_lock);
        va_end(args);
    }
};

static CaptureSession g;

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------
static void set_error(const wchar_t *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    EnterCriticalSection(&g.error_lock);
    _vsnwprintf_s(g.last_error, _countof(g.last_error), _TRUNCATE, fmt, args);
    LeaveCriticalSection(&g.error_lock);
    va_end(args);
}

// ---------------------------------------------------------------------------
// Device enumeration
// ---------------------------------------------------------------------------
int audio_list_devices(audio_device_info_t **devices_out) {
    if (!devices_out) { set_error(L"devices_out is NULL"); return -1; }
    *devices_out = nullptr;

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool com_inited = SUCCEEDED(hr);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
        set_error(L"CoInitializeEx failed: 0x%08X", hr);
        return -1;
    }

    IMMDeviceEnumerator *enumerator = nullptr;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), (void **)&enumerator);
    if (FAILED(hr)) {
        set_error(L"CoCreateInstance(MMDeviceEnumerator) failed: 0x%08X", hr);
        if (com_inited) CoUninitialize();
        return -1;
    }

    IMMDeviceCollection *collection = nullptr;
    hr = enumerator->EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, &collection);
    if (FAILED(hr)) {
        set_error(L"EnumAudioEndpoints failed: 0x%08X", hr);
        enumerator->Release();
        if (com_inited) CoUninitialize();
        return -1;
    }

    UINT count = 0;
    collection->GetCount(&count);

    auto *devices = new audio_device_info_t[count + 1];
    int out_idx = 0;

    {
        auto &d = devices[out_idx];
        wcscpy_s(d.name, L"Default Device");
        d.id = -1;
        d.max_channels = 2;
        d.default_sample_rate = 16000;
        out_idx++;
    }

    for (UINT i = 0; i < count; ++i) {
        IMMDevice *dev = nullptr;
        hr = collection->Item(i, &dev);
        if (FAILED(hr)) continue;

        IPropertyStore *props = nullptr;
        hr = dev->OpenPropertyStore(STGM_READ, &props);
        if (SUCCEEDED(hr)) {
            PROPVARIANT var;
            PropVariantInit(&var);
            hr = props->GetValue(PKEY_Device_FriendlyName, &var);
            if (SUCCEEDED(hr)) {
                auto &d = devices[out_idx];
                wcscpy_s(d.name, var.pwszVal);
                d.id = static_cast<int>(i);
                d.max_channels = 2;
                d.default_sample_rate = 48000;
                PropVariantClear(&var);
                out_idx++;
            }
            props->Release();
        }
        dev->Release();
    }

    collection->Release();
    enumerator->Release();
    if (com_inited) CoUninitialize();

    *devices_out = devices;
    return out_idx;
}

void audio_free_device_list(audio_device_info_t *devices) {
    delete[] devices;
}

// ---------------------------------------------------------------------------
// Format conversion helpers
// ---------------------------------------------------------------------------
static void convert_audio_raw(
    const BYTE *src, UINT32 src_frames,
    const WAVEFORMATEX *src_fmt,
    float *dst, size_t &dst_out)
{
    int src_ch   = src_fmt->nChannels;
    int src_sr   = src_fmt->nSamplesPerSec;
    int src_bps  = src_fmt->wBitsPerSample;
    bool is_float = (src_fmt->wFormatTag == WAVE_FORMAT_IEEE_FLOAT)
                 || (src_fmt->wFormatTag == WAVE_FORMAT_EXTENSIBLE);

    int dst_ch = g.target_channels;
    int dst_sr = g.target_sample_rate;
    double ratio = (double)dst_sr / (double)src_sr;

    size_t out = 0;

    for (UINT32 i = 0; i < src_frames; ++i) {
        float sample = 0.0f;
        int ch_to_mix = (src_ch > 2) ? 1 : src_ch;
        for (int ch = 0; ch < ch_to_mix; ++ch) {
            if (is_float) {
                sample += reinterpret_cast<const float *>(src)[i * src_ch + ch];
            } else if (src_bps == 16) {
                sample += reinterpret_cast<const short *>(src)[i * src_ch + ch] / 32768.0f;
            } else if (src_bps == 8) {
                sample += reinterpret_cast<const BYTE *>(src)[i * src_ch + ch] / 128.0f - 1.0f;
            }
        }
        if (ch_to_mix > 0) sample /= (float)ch_to_mix;

        double dst_pos = (double)i * ratio;
        size_t idx = (size_t)dst_pos;
        dst[idx] = sample;
        if (idx + 1 > out) out = idx + 1;
        if (out >= kMaxBlockFrames) break;
    }

    dst_out = out;
}

static void push_audio(const BYTE *data, UINT32 frames) {
    if (g.need_conversion) {
        float converted[kMaxBlockFrames];
        size_t dst_samples = 0;
        convert_audio_raw(data, frames, &g.actual_format, converted, dst_samples);
        g.ring->write(converted, dst_samples);
    } else {
        size_t n = static_cast<size_t>(frames) * g.channels;
        g.ring->write(reinterpret_cast<const float *>(data), n);
    }
}

// ---------------------------------------------------------------------------
// audio_init
// ---------------------------------------------------------------------------
int audio_init(int device_id, int sample_rate, int channels, int block_ms) {
    if (sample_rate != 16000 && sample_rate != 48000) {
        set_error(L"sample_rate must be 16000 or 48000, got %d", sample_rate);
        return -1;
    }
    if (channels < 1 || channels > 2) {
        set_error(L"channels must be 1 or 2, got %d", channels);
        return -1;
    }
    if (block_ms < 10 || block_ms > 1000) {
        set_error(L"block_ms must be in [10, 1000], got %d", block_ms);
        return -1;
    }

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
        set_error(L"CoInitializeEx failed: 0x%08X", hr);
        return -2;
    }

    IMMDeviceEnumerator *enumerator = nullptr;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), (void **)&enumerator);
    if (FAILED(hr)) {
        set_error(L"CoCreateInstance(MMDeviceEnumerator) failed: 0x%08X", hr);
        return -3;
    }

    IMMDevice *device = nullptr;
    if (device_id == -1) {
        hr = enumerator->GetDefaultAudioEndpoint(eCapture, eConsole, &device);
    } else {
        IMMDeviceCollection *collection = nullptr;
        hr = enumerator->EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, &collection);
        if (SUCCEEDED(hr)) {
            hr = collection->Item(device_id, &device);
            collection->Release();
        }
    }

    if (FAILED(hr) || !device) {
        set_error(L"Device not found (id=%d, hr=0x%08X)", device_id, hr);
        enumerator->Release();
        return -4;
    }

    IAudioClient *audio_client = nullptr;
    hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                          (void **)&audio_client);
    if (FAILED(hr)) {
        set_error(L"Activate(IAudioClient) failed: 0x%08X", hr);
        device->Release();
        enumerator->Release();
        return -5;
    }

    // --- Build requested format ---
    WAVEFORMATEXTENSIBLE wfx = {};
    wfx.Format.cbSize               = 22;
    wfx.Format.wFormatTag           = WAVE_FORMAT_EXTENSIBLE;
    wfx.Format.nChannels            = static_cast<WORD>(channels);
    wfx.Format.nSamplesPerSec       = static_cast<DWORD>(sample_rate);
    wfx.Format.wBitsPerSample       = 32;
    wfx.Format.nBlockAlign          = static_cast<WORD>(channels * 4);
    wfx.Format.nAvgBytesPerSec      = static_cast<DWORD>(sample_rate) * channels * 4;
    wfx.Samples.wValidBitsPerSample = 32;
    wfx.dwChannelMask               = (channels == 1) ? SPEAKER_FRONT_CENTER
                                                      : (SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT);
    wfx.SubFormat                   = KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;

    REFERENCE_TIME hns_buf = static_cast<REFERENCE_TIME>(block_ms) * 20000;

    // Try requested format first
    hr = audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, hns_buf, 0,
                                  (WAVEFORMATEX *)&wfx, nullptr);

    if (SUCCEEDED(hr)) {
        g.actual_format = wfx.Format;
    } else {
        // Fallback: get native mix format and convert
        WAVEFORMATEX *pwfx = nullptr;
        hr = audio_client->GetMixFormat(&pwfx);
        if (FAILED(hr) || !pwfx) {
            set_error(L"GetMixFormat failed: 0x%08X", hr);
            audio_client->Release();
            device->Release();
            enumerator->Release();
            return -6;
        }

        // Copy full format (may be WAVEFORMATEXTENSIBLE)
        size_t sz = sizeof(WAVEFORMATEX) + pwfx->cbSize;
        if (sz > sizeof(g.actual_fmt_ext)) sz = sizeof(g.actual_fmt_ext);
        memcpy(&g.actual_fmt_ext, pwfx, sz);
        g.actual_format = g.actual_fmt_ext.Format;
        CoTaskMemFree(pwfx);

        hr = audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, hns_buf, 0,
                                      (WAVEFORMATEX *)&g.actual_fmt_ext, nullptr);
        if (FAILED(hr)) {
            hr = audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, 0, 0,
                                          (WAVEFORMATEX *)&g.actual_fmt_ext, nullptr);
        }

        if (FAILED(hr)) {
            set_error(L"Initialize(mix %dHz/%dch/%dbit fmt=0x%04X cb=%d) failed: 0x%08X",
                      (int)g.actual_format.nSamplesPerSec, (int)g.actual_format.nChannels,
                      (int)g.actual_format.wBitsPerSample, (int)g.actual_format.wFormatTag,
                      (int)g.actual_format.cbSize, hr);
            audio_client->Release();
            device->Release();
            enumerator->Release();
            return -7;
        }

        g.need_conversion = true;
        g.target_sample_rate = sample_rate;
        g.target_channels    = channels;
    }

    IAudioCaptureClient *capture_client = nullptr;
    hr = audio_client->GetService(__uuidof(IAudioCaptureClient),
                                  (void **)&capture_client);
    if (FAILED(hr)) {
        set_error(L"GetService(IAudioCaptureClient) failed: 0x%08X", hr);
        audio_client->Release();
        device->Release();
        enumerator->Release();
        return -8;
    }

    g.device_id       = device_id;
    g.sample_rate     = sample_rate;
    g.channels        = channels;
    g.block_ms        = block_ms;
    g.block_samples   = sample_rate * channels * block_ms / 1000;
    g.enumerator      = enumerator;
    g.device          = device;
    g.audio_client    = audio_client;
    g.capture_client  = capture_client;
    g.ring            = new RingBuffer<float, kRingCapacity>();

    return 0;
}

// ---------------------------------------------------------------------------
// Capture thread
// ---------------------------------------------------------------------------
static DWORD WINAPI capture_thread_proc(LPVOID) {
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr)) {
        g.set_error(L"CoInitializeEx on capture thread failed: 0x%08X", hr);
        return 1;
    }

    hr = g.audio_client->Start();
    if (FAILED(hr)) {
        g.set_error(L"IAudioClient::Start failed: 0x%08X", hr);
        CoUninitialize();
        return 2;
    }

    LARGE_INTEGER freq, next_cb;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&next_cb);
    LONGLONG cb_ticks = freq.QuadPart * g.block_ms / 1000;
    next_cb.QuadPart += cb_ticks;

    while (g.running) {
        UINT32 packet_size = 0;
        hr = g.capture_client->GetNextPacketSize(&packet_size);

        while (SUCCEEDED(hr) && packet_size > 0) {
            BYTE   *data = nullptr;
            UINT32  frames = 0;
            DWORD   flags = 0;
            hr = g.capture_client->GetBuffer(&data, &frames, &flags, nullptr, nullptr);

            if (SUCCEEDED(hr)) {
                if (!(flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
                    push_audio(data, frames);
                }
                g.capture_client->ReleaseBuffer(frames);
            }
            g.capture_client->GetNextPacketSize(&packet_size);
        }

        LARGE_INTEGER now;
        QueryPerformanceCounter(&now);
        if (now.QuadPart >= next_cb.QuadPart) {
            float block[kMaxBlockFrames];
            size_t read = g.ring->read(block, kMaxBlockFrames);
            if (read > 0 && g.callback) {
                g.callback(block, static_cast<int>(read), g.sample_rate);
            }

            next_cb.QuadPart += cb_ticks;
            if (next_cb.QuadPart <= now.QuadPart) {
                next_cb.QuadPart = now.QuadPart + cb_ticks;
            }
        }

        Sleep(kPollIntervalMs);
    }

    // Final flush
    {
        float remaining[kMaxBlockFrames];
        size_t read = g.ring->read(remaining, kMaxBlockFrames);
        if (read > 0 && g.callback) {
            g.callback(remaining, static_cast<int>(read), g.sample_rate);
        }
    }

    g.audio_client->Stop();
    CoUninitialize();
    return 0;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
int audio_start(audio_callback_t callback) {
    if (g.running) { set_error(L"Already capturing"); return -1; }
    if (!g.audio_client) { set_error(L"Not initialized — call audio_init first"); return -2; }
    if (!callback) { set_error(L"callback is NULL"); return -3; }

    g.callback = callback;
    g.running  = 1;
    g.ring->reset();

    g.thread = CreateThread(nullptr, 0, capture_thread_proc, nullptr, 0, nullptr);
    if (!g.thread) {
        g.running = 0;
        set_error(L"CreateThread failed: error %lu", GetLastError());
        return -4;
    }
    SetThreadPriority(g.thread, THREAD_PRIORITY_HIGHEST);
    return 0;
}

int audio_stop(void) {
    if (!g.running) return 0;
    g.running = 0;
    if (g.thread) {
        WaitForSingleObject(g.thread, 5000);
        CloseHandle(g.thread);
        g.thread = nullptr;
    }
    g.callback = nullptr;
    return 0;
}

void audio_close(void) {
    if (g.running) audio_stop();
    delete g.ring;  g.ring = nullptr;
    if (g.capture_client) { g.capture_client->Release(); g.capture_client = nullptr; }
    if (g.audio_client)   { g.audio_client->Release();   g.audio_client   = nullptr; }
    if (g.device)         { g.device->Release();         g.device         = nullptr; }
    if (g.enumerator)     { g.enumerator->Release();     g.enumerator     = nullptr; }
}

const wchar_t *audio_last_error(void) {
    return g.last_error;
}
