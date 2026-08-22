#pragma once
#include <stdint.h>
#include <string.h>

namespace phonics_game {
struct PackedAudioAsset { const char* id; uint32_t offset; uint32_t length; };
constexpr const char* kAudioPackSha256 = "563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72";
constexpr uint8_t kAudioPackSha256Bytes[32] = {0x56, 0x39, 0x43, 0x40, 0x24, 0x70, 0xea, 0xda, 0x01, 0x50, 0xe7, 0x47, 0x20, 0x08, 0x6d, 0x33, 0xef, 0x99, 0x21, 0xd8, 0xb0, 0x7e, 0x58, 0xe1, 0x42, 0x47, 0xf1, 0x8e, 0x91, 0x75, 0xea, 0x72};
constexpr uint32_t kAudioPackBytes = 950976u;
constexpr uint16_t kPackedAudioAssetCount = 42;
constexpr PackedAudioAsset kPackedAudioAssets[] = {
  {"cowboy_a", 32u, 26624u},
  {"cowboy_b", 26656u, 15018u},
  {"cowboy_c", 41674u, 15018u},
  {"cowboy_d", 56692u, 15018u},
  {"cowboy_e", 71710u, 26624u},
  {"cowboy_f", 98334u, 15018u},
  {"cowboy_g", 113352u, 15018u},
  {"cowboy_h", 128370u, 15018u},
  {"cowboy_i", 143388u, 26624u},
  {"cowboy_j", 170012u, 15018u},
  {"cowboy_k", 185030u, 15018u},
  {"cowboy_l", 200048u, 17066u},
  {"cowboy_m", 217114u, 15018u},
  {"cowboy_n", 232132u, 15018u},
  {"cowboy_o", 247150u, 26624u},
  {"cowboy_p", 273774u, 15018u},
  {"cowboy_q", 288792u, 15018u},
  {"cowboy_r", 303810u, 16384u},
  {"cowboy_s", 320194u, 15018u},
  {"cowboy_t", 335212u, 15018u},
  {"cowboy_u", 350230u, 27990u},
  {"cowboy_v", 378220u, 15018u},
  {"cowboy_w", 393238u, 15018u},
  {"cowboy_x", 408256u, 15018u},
  {"cowboy_y", 423274u, 18432u},
  {"cowboy_z", 441706u, 15018u},
  {"prompt_which_one_says", 456724u, 30422u},
  {"prompt_can_you_find", 487146u, 19154u},
  {"prompt_which_letter_makes", 506300u, 28152u},
  {"prompt_tap_the_one_that_says", 534452u, 38978u},
  {"prompt_listen_which_one_says", 573430u, 39370u},
  {"nudge_have_another_listen", 612800u, 27254u},
  {"nudge_take_your_time", 640054u, 67042u},
  {"nudge_listen_once_more", 707096u, 29684u},
  {"nudge_which_one_do_you_think", 736780u, 29646u},
  {"wrong_no_no", 766426u, 26562u},
  {"wrong_not_it_try_again", 792988u, 48942u},
  {"wrong_try_the_other_one", 841930u, 26518u},
  {"praise_nice_job", 868448u, 23834u},
  {"praise_great_work", 892282u, 20918u},
  {"praise_you_got_it", 913200u, 21970u},
  {"praise_thats_it", 935170u, 15806u},
};
inline const PackedAudioAsset* findPackedAudioAsset(const char* id) {
  for (const auto& asset : kPackedAudioAssets) {
    if (strcmp(asset.id, id) == 0) return &asset;
  }
  return nullptr;
}
}  // namespace phonics_game
