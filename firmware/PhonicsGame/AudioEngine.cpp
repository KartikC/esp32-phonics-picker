#include "AudioEngine.h"

#include <Arduino.h>
#include <ESP_I2S.h>
#include <Wire.h>
#include <atomic>
#include <esp_partition.h>
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "AudioAssetIndex.h"
#include "es8311.h"
#include "pin_config.h"

namespace phonics_game {
namespace {

constexpr uint32_t kSampleRate = 16000;
constexpr size_t kMonoChunkSamples = 256;  // 16 ms: keeps cancellation responsive.
constexpr size_t kGapFrames = 640;         // 40 ms at 16 kHz.
constexpr uint32_t kEdgeFadeFrames = 64;   // 4 ms removes start/end ticks.
// Match managed logical volume 100 on the V2 BSP. esp_codec_dev maps 100 to
// 0 dB. Its 3.3 V DAC / 5.0 V PA calibration contributes -3.61 dB, so the
// codec target is +3.61 dB. On the ES8311's 0.5 dB register curve that rounds
// down to DAC_REG32 = 0xC6 (+3.5 dB). The authored assets peak at -4 dBTP,
// leaving roughly 0.5 dB of digital headroom at this substantially louder
// setting.
constexpr uint8_t kCodecVolume100Register = 0xC6;

struct PackHeader {
  char magic[8];
  uint32_t version;
  uint32_t assetCount;
  uint32_t sampleRate;
  uint32_t payloadBytes;
  uint8_t reserved[8];
};
static_assert(sizeof(PackHeader) == 32, "audio pack header layout changed");

struct AudioCommand {
  const PackedAudioAsset* first;
  const PackedAudioAsset* second;
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
bool initialized = false;
bool audioSuspended = false;
int16_t monoBuffer[kMonoChunkSamples];
int16_t stereoBuffer[kMonoChunkSamples * 2];
uint8_t verificationBuffer[4096];
constexpr int16_t kStereoSilence[kMonoChunkSamples * 2] = {};

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

bool stream(const PackedAudioAsset* asset, uint32_t commandGeneration) {
  if (!asset) return true;
  uint32_t position = 0;
  const uint32_t totalSamples = asset->length / sizeof(int16_t);
  while (position < asset->length && current(commandGeneration)) {
    const size_t chunk = min(static_cast<uint32_t>(sizeof(monoBuffer)),
                             asset->length - position);
    memcpy(monoBuffer, audioPackBuffer + asset->offset + position, chunk);
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
    if (i2s.write(stereoBuffer, stereoBytes) != stereoBytes) return false;
    position += chunk;
  }
  if (current(commandGeneration)) return true;
  resetOutputToSilence();
  return false;
}

void gap(uint32_t commandGeneration) {
  if (!current(commandGeneration)) return;
  size_t remaining = kGapFrames;
  while (remaining && current(commandGeneration)) {
    const size_t frames = min(remaining, kMonoChunkSamples);
    i2s.write(kStereoSilence, frames * 2 * sizeof(int16_t));
    remaining -= frames;
  }
}

void audioTask(void*) {
  AudioCommand command;
  while (true) {
    if (xQueueReceive(commandQueue, &command, portMAX_DELAY) != pdTRUE) continue;
    audioTaskBusy.store(true, std::memory_order_release);
    if (current(command.generation)) {
      stream(command.first, command.generation);
      if (command.second && current(command.generation)) {
        gap(command.generation);
        stream(command.second, command.generation);
      }
      gap(command.generation);
    }
    audioTaskBusy.store(false, std::memory_order_release);
  }
}

void enqueue(const char* firstId, const char* secondId) {
  if (!initialized ||
      !acceptingCommands.load(std::memory_order_acquire)) return;
  AudioCommand command{
      findPackedAudioAsset(firstId),
      secondId ? findPackedAudioAsset(secondId) : nullptr,
      generation.fetch_add(1, std::memory_order_acq_rel) + 1,
  };
  if (!command.first || (secondId && !command.second)) return;
  xQueueOverwrite(commandQueue, &command);
}

}  // namespace

bool AudioEngine::begin() {
  pinMode(PA, OUTPUT);
  digitalWrite(PA, LOW);

  partition = esp_partition_find_first(
      ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_FAT, "ffat");
  if (!verifyPack() || !loadPackToPsram()) return false;

  i2s.setPins(I2S_BCK_IO, I2S_WS_IO, I2S_DO_IO, I2S_DI_IO, I2S_MCK_IO);
  if (!i2s.begin(I2S_MODE_STD, kSampleRate, I2S_DATA_BIT_WIDTH_16BIT,
                 I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
    return false;
  }

  codec = es8311_create(0, ES8311_ADDRRES_0);
  const es8311_clock_config_t clockConfig = {
      .mclk_inverted = false,
      .sclk_inverted = false,
      .mclk_from_mclk_pin = true,
      .mclk_frequency = static_cast<int>(kSampleRate * 256),
      .sample_frequency = static_cast<int>(kSampleRate),
  };
  if (!codec || es8311_init(codec, &clockConfig, ES8311_RESOLUTION_16,
                            ES8311_RESOLUTION_16) != ESP_OK ||
      es8311_sample_frequency_config(codec, clockConfig.mclk_frequency,
                                     clockConfig.sample_frequency) != ESP_OK ||
      es8311_voice_volume_register_set(codec, kCodecVolume100Register) != ESP_OK ||
      es8311_voice_mute(codec, true) != ESP_OK) {
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
  acceptingCommands.store(true, std::memory_order_release);
#ifdef PHONICS_AUDIO_DIAGNOSTIC
  stream(findPackedAudioAsset("prompt_which_one_says"), 0);
  gap(0);
  stream(findPackedAudioAsset("cowboy_a"), 0);
  gap(0);
#endif
  return true;
}

bool AudioEngine::ready() { return initialized && !audioSuspended; }

bool AudioEngine::suspend() {
  if (!initialized) return false;
  if (audioSuspended) return true;

  // Stop new work first, then invalidate both queued and currently streaming
  // audio. A chunk is only 16 ms, so the bounded acknowledgement normally
  // completes almost immediately without tearing down the cross-core task.
  acceptingCommands.store(false, std::memory_order_release);
  generation.fetch_add(1, std::memory_order_acq_rel);
  xQueueReset(commandQueue);
  const bool muted = codec && es8311_voice_mute(codec, true) == ESP_OK;
  digitalWrite(PA, LOW);
  const uint32_t waitStartedAtMs = millis();
  while (audioTaskBusy.load(std::memory_order_acquire) &&
         millis() - waitStartedAtMs < 120) {
    delay(1);
  }
  const bool idle = !audioTaskBusy.load(std::memory_order_acquire);
  // Never disable the I2S channel while the other core may be in i2s.write().
  const bool silenced = idle && resetOutputToSilence();
  audioSuspended = true;
  return muted && idle && silenced;
}

bool AudioEngine::resume() {
  if (!initialized) return false;
  if (!audioSuspended) return true;

  digitalWrite(PA, LOW);
  const bool muted = codec && es8311_voice_mute(codec, true) == ESP_OK;
  const uint32_t waitStartedAtMs = millis();
  while (audioTaskBusy.load(std::memory_order_acquire) &&
         millis() - waitStartedAtMs < 120) {
    delay(1);
  }
  const bool idle = !audioTaskBusy.load(std::memory_order_acquire);
  const bool silenced = idle && resetOutputToSilence();
  if (!(muted && idle && silenced)) return false;
  digitalWrite(PA, HIGH);
  delay(10);
  const bool unmuted = codec && es8311_voice_mute(codec, false) == ESP_OK;
  if (!unmuted) {
    digitalWrite(PA, LOW);
    return false;
  }
  audioSuspended = false;
  acceptingCommands.store(true, std::memory_order_release);
  return true;
}

void AudioEngine::play(const char* assetId) { enqueue(assetId, nullptr); }

void AudioEngine::playSequence(const char* firstId, const char* secondId) {
  enqueue(firstId, secondId);
}

}  // namespace phonics_game
