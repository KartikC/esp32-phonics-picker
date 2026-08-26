#include "AudioEngine.h"

#include <Arduino.h>
#include <ESP_I2S.h>
#include <Wire.h>
#include <atomic>
#include <esp_partition.h>
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "AudioAssetIndex.h"
#include "AudioIdlePolicy.h"
#include "es8311.h"
#include "pin_config.h"

namespace phonics_game {
namespace {

constexpr uint32_t kSampleRate = 16000;
constexpr size_t kMonoChunkSamples = 256;  // 16 ms: keeps cancellation responsive.
constexpr size_t kGapFrames = 640;         // 40 ms at 16 kHz.
// The ES8311 and external PA need more than the 10 ms GPIO/codec setup delay
// before speech is acoustically stable. Feed silence after unmuting so an
// asset that begins at sample zero cannot lose its opening consonant.
constexpr size_t kWakeSettleFrames = 1920;  // 120 ms at 16 kHz.
constexpr uint32_t kEdgeFadeFrames = 64;   // 4 ms removes start/end ticks.
constexpr uint8_t kMaxAudioLayers = 2;
constexpr uint32_t kRewardMixFrames = 42240;  // 2.64 s at 16 kHz.
// Keep five decibels of additional DAC/speaker headroom. The former logical
// 100 setting used DAC_REG32 = 0xC6 and left only about 0.5 dB above the
// authored -4 dBTP speech peaks. Each ES8311 step is 0.5 dB, so 0xBC is 5 dB
// lower while preserving every authored category's relative level.
constexpr uint8_t kCodecVolume90Register = 0xBC;
constexpr es8311_clock_config_t kCodecClockConfig = {
    .mclk_inverted = false,
    .sclk_inverted = false,
    .mclk_from_mclk_pin = true,
    .mclk_frequency = static_cast<int>(kSampleRate * 256),
    .sample_frequency = static_cast<int>(kSampleRate),
};

struct PackHeader {
  char magic[8];
  uint32_t version;
  uint32_t assetCount;
  uint32_t sampleRate;
  uint32_t payloadBytes;
  uint8_t reserved[8];
};
static_assert(sizeof(PackHeader) == 32, "audio pack header layout changed");

struct AudioLayer {
  const uint8_t* pcm;
  uint32_t length;
};

struct AudioCommand {
  AudioLayer layers[kMaxAudioLayers];
  uint8_t layerCount;
  uint32_t totalFrames;
  uint32_t generation;
};

I2SClass i2s;
es8311_handle_t codec = nullptr;
const esp_partition_t* partition = nullptr;
uint8_t* audioPackBuffer = nullptr;
QueueHandle_t commandQueue = nullptr;
std::atomic<uint32_t> generation{0};
std::atomic<bool> acceptingCommands{false};
std::atomic<bool> audioTaskBusy{false};
std::atomic<uint32_t> playbackFinishedAtMs{0};
std::atomic<bool> playbackHasFinished{false};
std::atomic<uint32_t> writeFailures{0};
bool initialized = false;
bool audioSuspended = false;
bool i2sClocksStopped = false;
bool outputPowered = false;
bool outputFault = false;
bool outputNeedsRestore = false;
uint32_t idlePowerDowns = 0;
int16_t monoBuffer[kMonoChunkSamples];
int16_t stereoBuffer[kMonoChunkSamples * 2];
// The reward renderer also uses PSRAM heavily. Stage the selected offline mix
// in deterministic internal RAM before drawing begins so display traffic can
// never starve the I2S stream.
DRAM_ATTR int16_t rewardPlaybackBuffer[kRewardMixFrames];
uint8_t verificationBuffer[4096];
constexpr int16_t kStereoSilence[kMonoChunkSamples * 2] = {};

bool writeSilenceFrames(size_t frames) {
  while (frames > 0) {
    const size_t chunkFrames = min(frames, kMonoChunkSamples);
    const size_t bytes = chunkFrames * 2 * sizeof(int16_t);
    if (i2s.write(kStereoSilence, bytes) != bytes) {
      writeFailures.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    frames -= chunkFrames;
  }
  return true;
}

bool current(uint32_t commandGeneration) {
  return generation.load(std::memory_order_acquire) == commandGeneration;
}

bool resetOutputToSilence() {
  i2s_chan_handle_t channel = i2s.txChan();
  if (!channel || i2s_channel_disable(channel) != ESP_OK) return false;
  size_t loaded = 0;
  const esp_err_t preloadResult = i2s_channel_preload_data(
      channel, kStereoSilence, sizeof(kStereoSilence), &loaded);
  const esp_err_t enableResult = i2s_channel_enable(channel);
  return preloadResult == ESP_OK && loaded > 0 && enableResult == ESP_OK;
}

bool configureCodecMuted() {
  return codec &&
      es8311_init(codec, &kCodecClockConfig, ES8311_RESOLUTION_16,
                  ES8311_RESOLUTION_16) == ESP_OK &&
      es8311_sample_frequency_config(codec, kCodecClockConfig.mclk_frequency,
                                     kCodecClockConfig.sample_frequency) == ESP_OK &&
      es8311_voice_volume_register_set(codec, kCodecVolume90Register) == ESP_OK &&
      es8311_voice_mute(codec, true) == ESP_OK;
}

bool powerDownOutput() {
  if (!outputPowered) return !outputFault;

  // The amp is hard-gated before clocks move. The codec is already fed a
  // trailing authored silence gap, then muted once more as a fail-safe.
  const bool muted = codec && es8311_voice_mute(codec, true) == ESP_OK;
  digitalWrite(PA, LOW);
  const bool silenced = resetOutputToSilence();
  const bool codecDown = codec && es8311_power_down(codec) == ESP_OK;
  i2s_chan_handle_t channel = i2s.txChan();
  const bool channelDown = channel && i2s_channel_disable(channel) == ESP_OK;
  i2sClocksStopped = channelDown;
  outputPowered = false;
  outputFault = !(muted && silenced && codecDown && channelDown);
  outputNeedsRestore = outputFault;
  return !outputFault;
}

bool powerUpOutput() {
  if (outputPowered && !outputNeedsRestore) return !outputFault;

  digitalWrite(PA, LOW);
  i2s_chan_handle_t channel = i2s.txChan();
  if (!channel ||
      (i2sClocksStopped && i2s_channel_enable(channel) != ESP_OK) ||
      !configureCodecMuted() || !resetOutputToSilence()) {
    if (channel && i2s_channel_disable(channel) == ESP_OK) {
      i2sClocksStopped = true;
    }
    outputPowered = false;
    outputFault = true;
    outputNeedsRestore = true;
    return false;
  }
  i2sClocksStopped = false;
  digitalWrite(PA, HIGH);
  delay(10);
  if (!codec || es8311_voice_mute(codec, false) != ESP_OK) {
    digitalWrite(PA, LOW);
    if (i2s_channel_disable(channel) == ESP_OK) i2sClocksStopped = true;
    outputPowered = false;
    outputFault = true;
    outputNeedsRestore = true;
    return false;
  }
  if (!writeSilenceFrames(kWakeSettleFrames)) {
    es8311_voice_mute(codec, true);
    digitalWrite(PA, LOW);
    if (i2s_channel_disable(channel) == ESP_OK) i2sClocksStopped = true;
    outputPowered = false;
    outputFault = true;
    outputNeedsRestore = true;
    return false;
  }
  outputPowered = true;
  outputFault = false;
  outputNeedsRestore = false;
  return true;
}

bool verifyPack() {
  PackHeader header{};
  if (!partition || partition->size < kAudioPackBytes ||
      esp_partition_read(partition, 0, &header, sizeof(header)) != ESP_OK ||
      memcmp(header.magic, "PHONICS1", 8) != 0 || header.version != 1 ||
      header.assetCount != kPackedAudioAssetCount ||
      header.sampleRate != kSampleRate ||
      header.payloadBytes != kAudioPackBytes - sizeof(PackHeader)) {
    return false;
  }

  uint32_t expectedOffset = sizeof(PackHeader);
  for (const auto& asset : kPackedAudioAssets) {
    if (asset.offset != expectedOffset || asset.length == 0 ||
        (asset.offset & 1u) != 0 || (asset.length & 1u) != 0 ||
        asset.offset > kAudioPackBytes ||
        asset.length > kAudioPackBytes - asset.offset) {
      return false;
    }
    expectedOffset = asset.offset + asset.length;
  }
  if (expectedOffset != kAudioPackBytes) return false;

  mbedtls_sha256_context hashContext;
  uint8_t digest[32];
  mbedtls_sha256_init(&hashContext);
  int result = mbedtls_sha256_starts(&hashContext, 0);
  for (uint32_t offset = 0; result == 0 && offset < kAudioPackBytes;) {
    const size_t chunk = min(static_cast<uint32_t>(sizeof(verificationBuffer)),
                             kAudioPackBytes - offset);
    if (esp_partition_read(partition, offset, verificationBuffer, chunk) != ESP_OK) {
      result = -1;
      break;
    }
    result = mbedtls_sha256_update(&hashContext, verificationBuffer, chunk);
    offset += chunk;
  }
  if (result == 0) result = mbedtls_sha256_finish(&hashContext, digest);
  mbedtls_sha256_free(&hashContext);
  return result == 0 && memcmp(digest, kAudioPackSha256Bytes, sizeof(digest)) == 0;
}

bool loadPackToPsram() {
  audioPackBuffer = static_cast<uint8_t*>(
      heap_caps_malloc(kAudioPackBytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  if (!audioPackBuffer) return false;
  for (uint32_t offset = 0; offset < kAudioPackBytes;) {
    const size_t chunk = min(static_cast<uint32_t>(sizeof(verificationBuffer)),
                             kAudioPackBytes - offset);
    if (esp_partition_read(partition, offset, audioPackBuffer + offset, chunk) != ESP_OK) {
      heap_caps_free(audioPackBuffer);
      audioPackBuffer = nullptr;
      return false;
    }
    offset += chunk;
  }
  return true;
}

bool stream(const uint8_t* pcm, uint32_t length,
            uint32_t commandGeneration) {
  if (!pcm || length == 0) return true;
  uint32_t position = 0;
  const uint32_t totalSamples = length / sizeof(int16_t);
  while (position < length && current(commandGeneration)) {
    const size_t chunk = min(static_cast<uint32_t>(sizeof(monoBuffer)),
                             length - position);
    memcpy(monoBuffer, pcm + position, chunk);
    const size_t samples = chunk / sizeof(int16_t);
    for (size_t index = 0; index < samples; ++index) {
      const uint32_t sampleIndex = position / sizeof(int16_t) + index;
      const uint32_t endingFrames = totalSamples - 1 - sampleIndex;
      const uint32_t fadeFrames = min(min(sampleIndex, endingFrames), kEdgeFadeFrames);
      int32_t sample = monoBuffer[index] * static_cast<int32_t>(fadeFrames);
      sample /= kEdgeFadeFrames;
      const int16_t output = static_cast<int16_t>(sample);
      stereoBuffer[index * 2] = output;
      stereoBuffer[index * 2 + 1] = output;
    }
    const size_t stereoBytes = samples * 2 * sizeof(int16_t);
    if (i2s.write(stereoBuffer, stereoBytes) != stereoBytes) {
      writeFailures.fetch_add(1, std::memory_order_relaxed);
      resetOutputToSilence();
      return false;
    }
    position += chunk;
  }
  if (current(commandGeneration)) return true;
  resetOutputToSilence();
  return false;
}

bool gap(uint32_t commandGeneration) {
  if (!current(commandGeneration)) return false;
  size_t remaining = kGapFrames;
  while (remaining && current(commandGeneration)) {
    const size_t frames = min(remaining, kMonoChunkSamples);
    const size_t bytes = frames * 2 * sizeof(int16_t);
    if (i2s.write(kStereoSilence, bytes) != bytes) {
      writeFailures.fetch_add(1, std::memory_order_relaxed);
      resetOutputToSilence();
      return false;
    }
    remaining -= frames;
  }
  return remaining == 0;
}

void audioTask(void*) {
  AudioCommand command;
  while (true) {
    if (xQueueReceive(commandQueue, &command, portMAX_DELAY) != pdTRUE) continue;
    playbackHasFinished.store(false, std::memory_order_release);
    audioTaskBusy.store(true, std::memory_order_release);
    if (current(command.generation)) {
      bool playbackOk = false;
      if (command.layerCount == 1) {
        playbackOk = stream(command.layers[0].pcm, command.layers[0].length,
                            command.generation);
      } else {
        playbackOk = stream(command.layers[0].pcm, command.layers[0].length,
                            command.generation);
        if (playbackOk && current(command.generation)) {
          playbackOk = gap(command.generation) &&
              stream(command.layers[1].pcm, command.layers[1].length,
                     command.generation);
        }
      }
      if (playbackOk) gap(command.generation);
    }
    playbackFinishedAtMs.store(millis(), std::memory_order_release);
    playbackHasFinished.store(true, std::memory_order_release);
    audioTaskBusy.store(false, std::memory_order_release);
  }
}

bool addLayer(AudioCommand& command, const uint8_t* pcm, uint32_t length) {
  if (!pcm || length == 0 || command.layerCount >= kMaxAudioLayers) return false;
  command.layers[command.layerCount++] = AudioLayer{pcm, length};
  command.totalFrames += length / sizeof(int16_t);
  return true;
}

void submit(AudioCommand& command) {
  if (!initialized ||
      audioSuspended ||
      !acceptingCommands.load(std::memory_order_acquire)) return;
  if (command.layerCount == 0 || command.totalFrames == 0) return;
  if (!outputPowered && !powerUpOutput()) return;
  command.generation =
      generation.fetch_add(1, std::memory_order_acq_rel) + 1;
  playbackHasFinished.store(false, std::memory_order_release);
  if (xQueueOverwrite(commandQueue, &command) != pdTRUE) {
    playbackFinishedAtMs.store(millis(), std::memory_order_release);
    playbackHasFinished.store(true, std::memory_order_release);
  }
}

void enqueue(const char* firstId, const char* secondId) {
  if (!initialized || audioSuspended ||
      !acceptingCommands.load(std::memory_order_acquire)) return;
  const PackedAudioAsset* first = findPackedAudioAsset(firstId);
  const PackedAudioAsset* second = secondId ? findPackedAudioAsset(secondId) : nullptr;
  if (!first || (secondId && !second)) return;
  AudioCommand command{};
  addLayer(command, audioPackBuffer + first->offset, first->length);
  if (second) {
    addLayer(command, audioPackBuffer + second->offset, second->length);
    command.totalFrames += kGapFrames;
  }
  // Idle power-down is transparent to callers: submit brings up muted clocks,
  // primes silence, enables the amp, and only then exposes PCM to the task.
  submit(command);
}

void enqueuePreparedReward(const char* rewardMixId) {
  if (!initialized || audioSuspended ||
      !acceptingCommands.load(std::memory_order_acquire)) return;
  const PackedAudioAsset* asset = findPackedAudioAsset(rewardMixId);
  if (!asset || asset->length != sizeof(rewardPlaybackBuffer)) return;

  // dispatch() calls this before its first reward-frame draw. The only PSRAM
  // operation in the celebration path therefore finishes before the display
  // begins reading and flushing its animated framebuffer.
  memcpy(rewardPlaybackBuffer, audioPackBuffer + asset->offset, asset->length);
  AudioCommand command{};
  addLayer(command, reinterpret_cast<const uint8_t*>(rewardPlaybackBuffer),
           asset->length);
  submit(command);
}

}  // namespace

bool AudioEngine::begin() {
  pinMode(PA, OUTPUT);
  digitalWrite(PA, LOW);

  partition = esp_partition_find_first(
      ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_FAT, "ffat");
  if (!verifyPack() || !loadPackToPsram()) return false;

  // Playback is output-only. Passing the board's unused DIN pin makes the
  // Arduino core allocate and clock a needless RX channel for the microphone.
  i2s.setPins(I2S_BCK_IO, I2S_WS_IO, I2S_DO_IO, -1, I2S_MCK_IO);
  if (!i2s.begin(I2S_MODE_STD, kSampleRate, I2S_DATA_BIT_WIDTH_16BIT,
                 I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
    return false;
  }

  codec = es8311_create(0, ES8311_ADDRRES_0);
  if (!configureCodecMuted()) {
    if (codec) {
      es8311_delete(codec);
      codec = nullptr;
    }
    i2s.end();
    return false;
  }

  if (!resetOutputToSilence()) {
    es8311_delete(codec);
    codec = nullptr;
    i2s.end();
    return false;
  }

  commandQueue = xQueueCreate(1, sizeof(AudioCommand));
  if (!commandQueue || xTaskCreatePinnedToCore(audioTask, "phonics-audio", 6144,
                                               nullptr, 2, nullptr, 0) != pdPASS) {
    if (commandQueue) {
      vQueueDelete(commandQueue);
      commandQueue = nullptr;
    }
    es8311_delete(codec);
    codec = nullptr;
    i2s.end();
    return false;
  }
  initialized = true;
  digitalWrite(PA, HIGH);
  delay(10);
  if (es8311_voice_mute(codec, false) != ESP_OK) {
    initialized = false;
    digitalWrite(PA, LOW);
    return false;
  }
  if (!writeSilenceFrames(kWakeSettleFrames)) {
    initialized = false;
    es8311_voice_mute(codec, true);
    digitalWrite(PA, LOW);
    return false;
  }
  outputPowered = true;
  outputFault = false;
  outputNeedsRestore = false;
  playbackFinishedAtMs.store(millis(), std::memory_order_release);
  playbackHasFinished.store(true, std::memory_order_release);
  acceptingCommands.store(true, std::memory_order_release);
#ifdef PHONICS_AUDIO_DIAGNOSTIC
  const PackedAudioAsset* diagnosticPrompt =
      findPackedAudioAsset("prompt_which_one_says");
  stream(audioPackBuffer + diagnosticPrompt->offset,
         diagnosticPrompt->length, 0);
  gap(0);
  const PackedAudioAsset* diagnosticPhonics = findPackedAudioAsset("cowboy_a");
  stream(audioPackBuffer + diagnosticPhonics->offset,
         diagnosticPhonics->length, 0);
  gap(0);
#endif
  return true;
}

bool AudioEngine::ready() {
  return initialized && !audioSuspended && !outputFault;
}

bool AudioEngine::suspend() {
  if (!initialized) return false;
  if (audioSuspended) return true;

  // Stop new work first, then invalidate both queued and currently streaming
  // audio. A chunk is only 16 ms, so the bounded acknowledgement normally
  // completes almost immediately without tearing down the cross-core task.
  acceptingCommands.store(false, std::memory_order_release);
  generation.fetch_add(1, std::memory_order_acq_rel);
  xQueueReset(commandQueue);
  const bool muted = !outputPowered ||
                     (codec && es8311_voice_mute(codec, true) == ESP_OK);
  digitalWrite(PA, LOW);
  outputNeedsRestore = outputPowered;
  const uint32_t waitStartedAtMs = millis();
  while (audioTaskBusy.load(std::memory_order_acquire) &&
         millis() - waitStartedAtMs < 120) {
    delay(1);
  }
  const bool idle = !audioTaskBusy.load(std::memory_order_acquire);
  // Never disable the I2S channel while the other core may be in i2s.write().
  const bool poweredDown = idle && powerDownOutput();
  playbackHasFinished.store(false, std::memory_order_release);
  audioSuspended = true;
  return muted && poweredDown;
}

bool AudioEngine::resume() {
  if (!initialized) return false;
  if (!audioSuspended) return outputFault ? powerUpOutput() : true;
  const uint32_t waitStartedAtMs = millis();
  while (audioTaskBusy.load(std::memory_order_acquire) &&
         millis() - waitStartedAtMs < 120) {
    delay(1);
  }
  if (audioTaskBusy.load(std::memory_order_acquire)) return false;
  if (!powerUpOutput()) return false;
  audioSuspended = false;
  playbackFinishedAtMs.store(millis(), std::memory_order_release);
  playbackHasFinished.store(true, std::memory_order_release);
  acceptingCommands.store(true, std::memory_order_release);
  return true;
}

void AudioEngine::service(uint32_t nowMs) {
  if (!initialized || audioSuspended || outputFault || !outputPowered ||
      !commandQueue) {
    return;
  }
  const bool busy = audioTaskBusy.load(std::memory_order_acquire);
  const bool queued = uxQueueMessagesWaiting(commandQueue) > 0;
  const bool finished = playbackHasFinished.load(std::memory_order_acquire);
  const uint32_t finishedAt =
      playbackFinishedAtMs.load(std::memory_order_acquire);
  if (!AudioIdlePolicy::shouldPowerDown(
          nowMs, finishedAt, finished, busy, queued)) {
    return;
  }

  // Disarm before touching hardware so a failed transition cannot retry every
  // 8 ms. A future audio command performs a complete, synchronous recovery.
  playbackHasFinished.store(false, std::memory_order_release);
  if (powerDownOutput()) ++idlePowerDowns;
}

const char* AudioEngine::powerState() {
  if (!initialized) return "failed";
  if (outputFault) return "fault";
  if (audioSuspended) return "suspended";
  return outputPowered ? "on" : "idle";
}

uint32_t AudioEngine::idlePowerDownCount() { return idlePowerDowns; }

uint32_t AudioEngine::writeFailureCount() {
  return writeFailures.load(std::memory_order_relaxed);
}

void AudioEngine::play(const char* assetId) { enqueue(assetId, nullptr); }

void AudioEngine::playSequence(const char* firstId, const char* secondId) {
  enqueue(firstId, secondId);
}

void AudioEngine::playCelebration(const char* rewardMixId) {
  enqueuePreparedReward(rewardMixId);
}

}  // namespace phonics_game
