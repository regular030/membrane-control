#pragma once
#include "BoardConfig.h"

// No production pin mapping is included. Defining BASU_VERIFIED_PROFILE_HEADER must
// name a reviewed header providing basu::compiledBoardConfig(). A GUI cannot do this.
#ifdef BASU_VERIFIED_PROFILE_HEADER
#include BASU_VERIFIED_PROFILE_HEADER
#else
namespace basu {
inline BoardConfig compiledBoardConfig() { return BoardConfig{}; }
}
#endif
