#include <unity.h>
#include "BluetoothControlSession.h"

using namespace basu;

void setUp() {}
void tearDown() {}

void test_link_accepts_only_one_authorized_peer() {
  BluetoothLink link;
  TEST_ASSERT_FALSE(link.open(7, false));
  TEST_ASSERT_FALSE(link.open(0, true));
  TEST_ASSERT_TRUE(link.open(7, true));
  const auto active = link.token();
  TEST_ASSERT_FALSE(link.open(9, true));
  TEST_ASSERT_FALSE(link.close(9));
  TEST_ASSERT_TRUE(link.current(active));
}

void test_disconnect_discards_tokens_even_if_the_handle_is_reused() {
  BluetoothLink link;
  TEST_ASSERT_TRUE(link.open(3, true));
  const auto stale = link.token();
  TEST_ASSERT_TRUE(link.close(3));
  TEST_ASSERT_EQUAL_UINT32(0, link.token().handle);
  TEST_ASSERT_TRUE(link.open(3, true));
  TEST_ASSERT_FALSE(link.current(stale));
  TEST_ASSERT_FALSE(link.invalidate(stale));
  TEST_ASSERT_TRUE(link.current(link.token()));
}

void test_queue_or_write_failure_revokes_owner_until_disconnect() {
  BluetoothLink link;
  TEST_ASSERT_TRUE(link.open(5, true));
  const auto active = link.token();
  TEST_ASSERT_TRUE(link.invalidate(active));
  TEST_ASSERT_FALSE(link.current(active));
  TEST_ASSERT_EQUAL_UINT32(0, link.token().handle);
  TEST_ASSERT_FALSE(link.open(7, true));
  TEST_ASSERT_TRUE(link.close(5));
  TEST_ASSERT_TRUE(link.open(7, true));
}

void test_lease_requires_fresh_hello_and_heartbeat_on_every_session() {
  BluetoothCommandLease lease;
  lease.heartbeat(100);
  TEST_ASSERT_FALSE(lease.mayActuate(101));
  lease.hello();
  TEST_ASSERT_TRUE(lease.identified());
  TEST_ASSERT_FALSE(lease.mayActuate(102));
  lease.heartbeat(103);
  TEST_ASSERT_TRUE(lease.mayActuate(3102));
  TEST_ASSERT_FALSE(lease.mayActuate(3103));
  lease.heartbeat(3104);
  lease.hello();
  TEST_ASSERT_FALSE(lease.mayActuate(3105));
  lease.heartbeat(3106);
  lease.reset();
  TEST_ASSERT_FALSE(lease.identified());
  TEST_ASSERT_FALSE(lease.mayActuate(3107));
}

void test_lease_wraparound_uses_unsigned_age() {
  BluetoothCommandLease lease;
  lease.hello();
  lease.heartbeat(UINT32_MAX - 10);
  TEST_ASSERT_TRUE(lease.mayActuate(2988));
  TEST_ASSERT_FALSE(lease.mayActuate(2989));
}

void test_session_end_clears_valves_and_prevents_old_recipe_restart() {
  SafetyConfig safety;
  safety.simulation = false;
  safety.valveControlReady = true;
  Controller controller(safety);
  Recipe recipe;
  recipe.name = "Preceding connection";
  recipe.stepCount = 1;
  recipe.steps[0].name = "Step";
  recipe.steps[0].durationSeconds = 1;
  TEST_ASSERT_NULL(controller.load(recipe));
  Outputs commanded;
  commanded.valves[6] = true;
  TEST_ASSERT_NULL(controller.manualValves(commanded.valves, 10));
  TEST_ASSERT_TRUE(controller.outputs().valves[6]);
  controller.endControlSession();
  TEST_ASSERT_TRUE(controller.state() == State::Idle);
  for (bool valve : controller.outputs().valves) TEST_ASSERT_FALSE(valve);
  TEST_ASSERT_DOUBLE_WITHIN(0.001, 0, controller.outputs().pumpPercent);
  TEST_ASSERT_FALSE(controller.recipeLoaded());
  TEST_ASSERT_EQUAL_STRING("no recipe loaded", controller.start(20));
}

void test_session_end_preserves_watchdog_fault() {
  Controller controller;
  Outputs commanded;
  commanded.valves[0] = true;
  TEST_ASSERT_NULL(controller.manualValves(commanded.valves, 10));
  controller.tick(3010);
  controller.endControlSession();
  TEST_ASSERT_TRUE(controller.state() == State::Fault);
  TEST_ASSERT_EQUAL_STRING("heartbeat_timeout", controller.fault().c_str());
  TEST_ASSERT_FALSE(controller.outputs().valves[0]);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_link_accepts_only_one_authorized_peer);
  RUN_TEST(test_disconnect_discards_tokens_even_if_the_handle_is_reused);
  RUN_TEST(test_queue_or_write_failure_revokes_owner_until_disconnect);
  RUN_TEST(test_lease_requires_fresh_hello_and_heartbeat_on_every_session);
  RUN_TEST(test_lease_wraparound_uses_unsigned_age);
  RUN_TEST(test_session_end_clears_valves_and_prevents_old_recipe_restart);
  RUN_TEST(test_session_end_preserves_watchdog_fault);
  return UNITY_END();
}
