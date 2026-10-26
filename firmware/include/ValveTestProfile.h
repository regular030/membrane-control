#pragma once
#include "ValveTestConfig.h"

// A separate reviewed header provides basu::compiledValveTestConfig(). It must
// not share or unlock the production controller's BoardProfile approval.
#ifdef BASU_VALVE_PROFILE_HEADER
#include BASU_VALVE_PROFILE_HEADER
#else
namespace basu {
inline ValveTestConfig compiledValveTestConfig() { return ValveTestConfig{}; }
}
#endif
