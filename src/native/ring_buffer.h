#pragma once

#include <atomic>
#include <cstddef>
#include <algorithm>
#include <cstring>

template <typename T, size_t Capacity>
class RingBuffer {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");

    T buffer_[Capacity];
    static constexpr size_t kMask = Capacity - 1;
    std::atomic<size_t> write_pos_{0};
    std::atomic<size_t> read_pos_{0};

public:
    RingBuffer() = default;

    // Writer: returns bytes written (may be less than count if buffer full)
    size_t write(const T *data, size_t count) {
        size_t w = write_pos_.load(std::memory_order_relaxed);
        size_t r = read_pos_.load(std::memory_order_acquire);
        size_t available = Capacity - (w - r);
        size_t to_write = std::min(count, available);
        for (size_t i = 0; i < to_write; ++i) {
            buffer_[(w + i) & kMask] = data[i];
        }
        write_pos_.store(w + to_write, std::memory_order_release);
        return to_write;
    }

    // Reader: returns bytes read (0 if none available)
    size_t read(T *out, size_t max_count) {
        size_t r = read_pos_.load(std::memory_order_relaxed);
        size_t w = write_pos_.load(std::memory_order_acquire);
        size_t available = w - r;
        size_t to_read = std::min(max_count, available);
        for (size_t i = 0; i < to_read; ++i) {
            out[i] = buffer_[(r + i) & kMask];
        }
        read_pos_.store(r + to_read, std::memory_order_release);
        return to_read;
    }

    // How many elements available for reading
    size_t available() const {
        size_t w = write_pos_.load(std::memory_order_acquire);
        size_t r = read_pos_.load(std::memory_order_relaxed);
        return w - r;
    }

    void reset() {
        write_pos_.store(0, std::memory_order_release);
        read_pos_.store(0, std::memory_order_release);
    }

    // Prevent copying
    RingBuffer(const RingBuffer &) = delete;
    RingBuffer &operator=(const RingBuffer &) = delete;
};
