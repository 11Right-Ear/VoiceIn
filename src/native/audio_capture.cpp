#include "audio_capture.h"
#include "ring_buffer.h"

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>

#include <cstdio>

#pragma comment(lib, "ole32.lib")

// ---------------------------------------------------------------------------
// Ring buffer: 4 seconds at 16000 Hz mono = 64000 samples, next power of 2
// ---------------------------------------------------------------------------
static constexpr size_t kRingCapacity = 65536; // 2^16, ~256 KB
static constexpr int    kPollIntervalMs = 10;  // WASAPI poll granularity

// ---------------------------------------------------------------------------
// Per-session global state
// ---------------------------------------------------------------------------
struct CaptureSession {
    // User parameters
    int      device_id   = -1;
    int      sample_rate = 16000;
    int      channels    = 1;
    int      block_ms    = 100;

    // WASAPI COM objects
    IMMDeviceEnumerator  *enumerator     = nullptr;
    IMMDevice            *device         = nullptr;
    IAudioClient         *audio_client   = nullptr;
    IAudioCaptureClient  *capture_client = nullptr;

    // Requested format that WASAPI accepted
    WAVEFORMATEX          actual_format  = {};

    // Ring buffer + capture thread
    RingBuffer<float, kRingCapacity> *ring = nullptr;
    HANDLE                 thread       = nullptr;
    volatile LONG          running      = 0;
    audio_callback_t       callback     = nullptr;

    // Samples per block (for flushing to callback)
    int                    block_samples = 0;

    // Last error (thread safe via critical section)
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
// Helpers
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
// audio_list_devices
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

    auto *devices = new audio_device_info_t[count + 1]; // +1 for default
    int out_idx = 0;

    // Default device as id=-1
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
// audio_init
// ---------------------------------------------------------------------------
int audio_init(int device_id, int sample_rate, int channels, int block_ms) {
    // Basic validation
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

    // Validate the device exists by attempting to get it
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool com_inited = SUCCEEDED(hr);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
        set_error(L"CoInitializeEx failed: 0x%08X", hr);
        return -2;
    }

    IMMDeviceEnumerator *enumerator = nullptr;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), (void **)&enumerator);
    if (FAILED(hr)) {
        set_error(L"CoCreateInstance(MMDeviceEnumerator) failed: 0x%08X", hr);
        // COM stays initialized for capture thread use
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
        // COM stays initialized for capture thread use
        return -4;
    }

    // Create audio client
    IAudioClient *audio_client = nullptr;
    hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                          (void **)&audio_client);
    if (FAILED(hr)) {
        set_error(L"Activate(IAudioClient) failed: 0x%08X", hr);
        device->Release();
        enumerator->Release();
        // COM stays initialized for capture thread use
        return -5;
    }

    // Setup WAVEFORMATEXTENSIBLE for float32
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

    // Try to initialize with our format
    // hnsBufferDuration = 0 lets the engine pick; use block_ms * 2 for safety
    REFERENCE_TIME hns_buf = static_cast<REFERENCE_TIME>(block_ms) * 20000; // ms → hns, x2 margin

    hr = audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, hns_buf, 0,
                                  (WAVEFORMATEX *)&wfx, nullptr);

    if (FAILED(hr)) {
        // Fallback: try with plain WAVEFORMATEX (no extensible)
        WAVEFORMATEX wfx2 = {};
        wfx2.wFormatTag      = WAVE_FORMAT_IEEE_FLOAT;
        wfx2.nChannels       = static_cast<WORD>(channels);
        wfx2.nSamplesPerSec  = static_cast<DWORD>(sample_rate);
        wfx2.wBitsPerSample  = 32;
        wfx2.nBlockAlign     = static_cast<WORD>(channels * 4);
        wfx2.nAvgBytesPerSec = static_cast<DWORD>(sample_rate) * channels * 4;
        wfx2.cbSize          = 0;

        hr = audio_client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, hns_buf, 0,
                                      &wfx2, nullptr);
        if (SUCCEEDED(hr)) {
            g.actual_format = wfx2;
        }
    } else {
        g.actual_format = wfx.Format;
    }

    if (FAILED(hr)) {
        set_error(L"IAudioClient::Initialize failed: 0x%08X. "
                  L"Device may not support %d Hz float32",
                  hr, sample_rate);
        audio_client->Release();
        device->Release();
        enumerator->Release();
        // COM stays initialized for capture thread use
        return -6;
    }

    // Get capture client
    IAudioCaptureClient *capture_client = nullptr;
    hr = audio_client->GetService(__uuidof(IAudioCaptureClient),
                                  (void **)&capture_client);
    if (FAILED(hr)) {
        set_error(L"GetService(IAudioCaptureClient) failed: 0x%08X", hr);
        audio_client->Release();
        device->Release();
        enumerator->Release();
        // COM stays initialized for capture thread use
        return -7;
    }

    // Compute block size
    int block_samples = sample_rate * channels * block_ms / 1000;

    // Store session state
    g.device_id       = device_id;
    g.sample_rate     = sample_rate;
    g.channels        = channels;
    g.block_ms        = block_ms;
    g.block_samples   = block_samples;
    g.enumerator      = enumerator;
    g.device          = device;
    g.audio_client    = audio_client;
    g.capture_client  = capture_client;
    g.ring            = new RingBuffer<float, kRingCapacity>();

    // COM stays alive for capture thread; released in audio_close
    return 0;
}

// ---------------------------------------------------------------------------
// Capture thread procedure
// ---------------------------------------------------------------------------
static DWORD WINAPI capture_thread_proc(LPVOID /*param*/) {
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
        // Read all available WASAPI packets
        UINT32 packet_size = 0;
        hr = g.capture_client->GetNextPacketSize(&packet_size);

        while (SUCCEEDED(hr) && packet_size > 0) {
            BYTE   *data   = nullptr;
            UINT32  frames = 0;
            DWORD   flags  = 0;
            hr = g.capture_client->GetBuffer(&data, &frames, &flags, nullptr, nullptr);

            if (SUCCEEDED(hr)) {
                if (!(flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
                    // data is float32 interleaved PCM
                    size_t sample_count = static_cast<size_t>(frames) * g.channels;
                    g.ring->write(reinterpret_cast<const float *>(data), sample_count);
                }
                g.capture_client->ReleaseBuffer(frames);
            }
            g.capture_client->GetNextPacketSize(&packet_size);
        }

        // Flush accumulated ring-buffer data to callback every block_ms
        LARGE_INTEGER now;
        QueryPerformanceCounter(&now);
        if (now.QuadPart >= next_cb.QuadPart) {
            float block[16384];
            size_t read = g.ring->read(block, _countof(block));
            if (read > 0 && g.callback) {
                g.callback(block, static_cast<int>(read), g.sample_rate);
            }

            // Skip missed blocks
            next_cb.QuadPart += cb_ticks;
            if (next_cb.QuadPart <= now.QuadPart) {
                next_cb.QuadPart = now.QuadPart + cb_ticks;
            }
        }

        Sleep(kPollIntervalMs);
    }

    // Final flush of remaining buffered data
    {
        float remaining[16384];
        size_t read = g.ring->read(remaining, _countof(remaining));
        if (read > 0 && g.callback) {
            g.callback(remaining, static_cast<int>(read), g.sample_rate);
        }
    }

    g.audio_client->Stop();
    CoUninitialize();
    return 0;
}

// ---------------------------------------------------------------------------
// audio_start / audio_stop / audio_close
// ---------------------------------------------------------------------------
int audio_start(audio_callback_t callback) {
    if (g.running) {
        set_error(L"Already capturing");
        return -1;
    }
    if (!g.audio_client) {
        set_error(L"Not initialized — call audio_init first");
        return -2;
    }
    if (!callback) {
        set_error(L"callback is NULL");
        return -3;
    }

    g.callback = callback;
    g.running  = 1;
    g.ring->reset();

    g.thread = CreateThread(nullptr, 0, capture_thread_proc, nullptr, 0, nullptr);
    if (!g.thread) {
        g.running = 0;
        set_error(L"CreateThread failed: error %lu", GetLastError());
        return -4;
    }

    // Bump thread priority for low-latency audio
    SetThreadPriority(g.thread, THREAD_PRIORITY_HIGHEST);

    return 0;
}

int audio_stop(void) {
    if (!g.running) return 0;

    g.running = 0;
    if (g.thread) {
        WaitForSingleObject(g.thread, 5000); // 5s timeout
        CloseHandle(g.thread);
        g.thread = nullptr;
    }
    g.callback = nullptr;
    return 0;
}

void audio_close(void) {
    if (g.running) {
        audio_stop();
    }

    delete g.ring;
    g.ring = nullptr;

    if (g.capture_client)  { g.capture_client->Release(); g.capture_client = nullptr; }
    if (g.audio_client)    { g.audio_client->Release();   g.audio_client   = nullptr; }
    if (g.device)          { g.device->Release();         g.device         = nullptr; }
    if (g.enumerator)      { g.enumerator->Release();     g.enumerator     = nullptr; }
}

const wchar_t *audio_last_error(void) {
    return g.last_error;
}
