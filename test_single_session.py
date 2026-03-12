#!/usr/bin/env python3
"""Quick test: create 1 session, advance ticks, destroy."""
import grpc
import time
import sys

sys.path.insert(0, "/Users/berta/Projects/OpenRA-RL")
from openra_env.generated import rl_bridge_pb2, rl_bridge_pb2_grpc

ch = grpc.insecure_channel("localhost:9999", options=[("grpc.max_receive_message_length", 64*1024*1024)])
stub = rl_bridge_pb2_grpc.RLBridgeStub(ch)

print("Creating session...")
resp = stub.CreateSession(
    rl_bridge_pb2.CreateSessionRequest(map_name="singles.oramap", bots="Multi1:rl-agent,Multi0:beginner", seed=42),
    timeout=10,
)
sid = resp.session_id
print(f"Session: {sid}")

# Wait for bridge to be ready
for i in range(60):
    state = stub.GetState(rl_bridge_pb2.StateRequest(session_id=sid), timeout=5)
    if state.phase not in ("no_bridge", "waiting"):
        print(f"Ready: phase={state.phase} after {i*0.5:.1f}s")
        break
    time.sleep(0.5)
else:
    print(f"Timeout: phase={state.phase}")
    sys.exit(1)

# FastAdvance
print("Advancing 50 ticks...")
try:
    obs = stub.FastAdvance(rl_bridge_pb2.FastAdvanceRequest(ticks=50, session_id=sid), timeout=30)
    print(f"  tick={obs.tick}, done={obs.done}, cash={obs.economy.cash}, units={len(obs.units)}")
except Exception as e:
    print(f"FastAdvance failed: {e}")
    sys.exit(1)

print("Advancing 100 more ticks...")
try:
    obs = stub.FastAdvance(rl_bridge_pb2.FastAdvanceRequest(ticks=100, session_id=sid), timeout=30)
    print(f"  tick={obs.tick}, done={obs.done}, cash={obs.economy.cash}, units={len(obs.units)}")
except Exception as e:
    print(f"FastAdvance failed: {e}")
    sys.exit(1)

# Destroy
stub.DestroySession(rl_bridge_pb2.DestroySessionRequest(session_id=sid), timeout=10)
print("Session destroyed")
print("SUCCESS")
