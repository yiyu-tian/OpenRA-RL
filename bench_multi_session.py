#!/usr/bin/env python3
"""Benchmark latency for multi-session OpenRA daemon.

Measures:
  - Session creation (reset) latency
  - FastAdvance per-call latency
  - Session destroy latency
  - Concurrent throughput

Usage:
    python bench_multi_session.py [num_sessions] [ticks_per_advance] [num_advances]

Default: 64 sessions, 50 ticks/advance, 10 advances per session.
"""

import os
import subprocess
import sys
import time
import threading
import statistics
import grpc

sys.path.insert(0, os.path.dirname(__file__))

from openra_env.generated import rl_bridge_pb2, rl_bridge_pb2_grpc

OPENRA_DIR = os.path.join(os.path.dirname(__file__), "OpenRA")
GRPC_PORT = 9999
MAP_NAME = "singles.oramap"
BOTS = "Multi1:rl-agent,Multi0:beginner"


def start_daemon():
    env = os.environ.copy()
    env["DOTNET_ROLL_FORWARD"] = "LatestMajor"
    env["RL_GRPC_PORT"] = str(GRPC_PORT)

    cmd = [
        "dotnet", os.path.join(OPENRA_DIR, "bin", "OpenRA.dll"),
        f"Engine.EngineDir={OPENRA_DIR}",
        "Game.Mod=ra",
        "Game.Platform=Null",
        f"Launch.MultiSession={GRPC_PORT}",
    ]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=OPENRA_DIR, env=env,
    )
    print(f"Daemon PID={proc.pid}")
    return proc


def wait_for_daemon(channel, max_wait=30):
    stub = rl_bridge_pb2_grpc.RLBridgeStub(channel)
    for i in range(max_wait):
        try:
            stub.GetState(rl_bridge_pb2.StateRequest(), timeout=2.0)
            print(f"Daemon ready after {i+1}s")
            return True
        except grpc.RpcError:
            time.sleep(1)
    print("Daemon failed to start!")
    return False


def create_session_timed(stub, seed):
    """Create a session and wait until it's playing. Returns (session_id, latency_ms)."""
    t0 = time.monotonic()
    resp = stub.CreateSession(
        rl_bridge_pb2.CreateSessionRequest(
            map_name=MAP_NAME, bots=BOTS, seed=seed,
        ),
        timeout=60.0,
    )
    sid = resp.session_id

    # Poll until playing
    for _ in range(120):
        state = stub.GetState(
            rl_bridge_pb2.StateRequest(session_id=sid), timeout=5.0,
        )
        if state.phase == "playing":
            break
        time.sleep(0.25)

    latency = (time.monotonic() - t0) * 1000  # ms
    return sid, latency


def destroy_session_timed(stub, sid):
    """Destroy a session. Returns latency_ms."""
    t0 = time.monotonic()
    stub.DestroySession(
        rl_bridge_pb2.DestroySessionRequest(session_id=sid), timeout=10.0,
    )
    return (time.monotonic() - t0) * 1000


def advance_timed(stub, sid, ticks):
    """Single FastAdvance call. Returns (obs, latency_ms)."""
    t0 = time.monotonic()
    obs = stub.FastAdvance(
        rl_bridge_pb2.FastAdvanceRequest(ticks=ticks, session_id=sid),
        timeout=60.0,
    )
    latency = (time.monotonic() - t0) * 1000
    return obs, latency


def run_session_bench(stub, session_num, seed, ticks_per_advance, num_advances, results):
    """Full lifecycle benchmark for one session."""
    try:
        # Create
        sid, create_ms = create_session_timed(stub, seed)

        # Advances
        advance_latencies = []
        final_tick = 0
        for step in range(num_advances):
            obs, adv_ms = advance_timed(stub, sid, ticks_per_advance)
            advance_latencies.append(adv_ms)
            final_tick = obs.tick
            if obs.done:
                break

        # Destroy
        destroy_ms = destroy_session_timed(stub, sid)

        results[session_num] = {
            "ok": True,
            "sid": sid,
            "create_ms": create_ms,
            "destroy_ms": destroy_ms,
            "advance_latencies": advance_latencies,
            "final_tick": final_tick,
            "num_advances": len(advance_latencies),
        }

    except Exception as e:
        results[session_num] = {"ok": False, "error": str(e)}
        print(f"  Session {session_num}: FAILED - {e}")


def fmt_stats(values, unit="ms"):
    """Format min/p50/p95/max stats."""
    if not values:
        return "N/A"
    s = sorted(values)
    p50 = statistics.median(s)
    p95 = s[int(len(s) * 0.95)] if len(s) >= 2 else s[-1]
    return f"min={min(s):.0f}{unit}  p50={p50:.0f}{unit}  p95={p95:.0f}{unit}  max={max(s):.0f}{unit}"


def main():
    num_sessions = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    ticks_per_advance = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    num_advances = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    print(f"=== Latency Benchmark: {num_sessions} sessions, {ticks_per_advance} ticks/advance, {num_advances} advances ===\n")

    daemon = start_daemon()

    try:
        channel = grpc.insecure_channel(
            f"localhost:{GRPC_PORT}",
            options=[
                ("grpc.max_receive_message_length", 64 * 1024 * 1024),
                ("grpc.max_send_message_length", 16 * 1024 * 1024),
            ],
        )

        if not wait_for_daemon(channel):
            return 1

        stub = rl_bridge_pb2_grpc.RLBridgeStub(channel)

        # === Phase 1: Serial create (measures reset latency) ===
        print(f"\n--- Phase 1: Creating {num_sessions} sessions (serial) ---")
        create_latencies = []
        session_ids = []
        for i in range(num_sessions):
            sid, create_ms = create_session_timed(stub, 42 + i)
            create_latencies.append(create_ms)
            session_ids.append(sid)
            if i < 3 or (i + 1) % 16 == 0:
                print(f"  [{i+1}/{num_sessions}] {sid}: {create_ms:.0f}ms")

        print(f"\nCreate (reset) latency: {fmt_stats(create_latencies)}")
        print(f"Total create wall time: {sum(create_latencies)/1000:.1f}s")

        # === Phase 2: Concurrent advances (measures advance latency under load) ===
        print(f"\n--- Phase 2: {num_advances} advances x {num_sessions} sessions (concurrent) ---")
        results = {}
        threads = []
        t_run = time.monotonic()

        for i, sid in enumerate(session_ids):
            t = threading.Thread(
                target=run_session_bench,
                args=(stub, i, 42 + i, ticks_per_advance, num_advances, results),
            )
            # Override: sessions already created, just run advances + destroy
            def run_advances_only(stub_, sid_, num_, tpa_, idx_, res_):
                try:
                    adv_lats = []
                    final_tick = 0
                    for step in range(num_):
                        obs, adv_ms = advance_timed(stub_, sid_, tpa_)
                        adv_lats.append(adv_ms)
                        final_tick = obs.tick
                        if obs.done:
                            break
                    destroy_ms = destroy_session_timed(stub_, sid_)
                    res_[idx_] = {
                        "ok": True, "sid": sid_,
                        "advance_latencies": adv_lats,
                        "destroy_ms": destroy_ms,
                        "final_tick": final_tick,
                        "num_advances": len(adv_lats),
                    }
                except Exception as e:
                    res_[idx_] = {"ok": False, "error": str(e)}
                    print(f"  Session {idx_}: FAILED - {e}")

            t = threading.Thread(
                target=run_advances_only,
                args=(stub, sid, num_advances, ticks_per_advance, i, results),
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=300)

        wall_run = time.monotonic() - t_run

        # === Results ===
        ok = sum(1 for r in results.values() if r.get("ok"))
        failed = num_sessions - ok

        all_advance = []
        all_destroy = []
        for r in results.values():
            if r.get("ok"):
                all_advance.extend(r["advance_latencies"])
                all_destroy.append(r["destroy_ms"])

        print(f"\n{'='*60}")
        print(f"RESULTS: {ok}/{num_sessions} sessions OK, {failed} failed")
        print(f"{'='*60}")
        print(f"\nCreate (reset) latency ({len(create_latencies)} samples):")
        print(f"  {fmt_stats(create_latencies)}")
        print(f"\nFastAdvance latency ({len(all_advance)} samples, {ticks_per_advance} ticks each):")
        print(f"  {fmt_stats(all_advance)}")
        print(f"\nDestroy latency ({len(all_destroy)} samples):")
        print(f"  {fmt_stats(all_destroy)}")
        print(f"\nConcurrent run phase: {wall_run:.1f}s wall clock for {ok}x{num_advances} advances")
        if all_advance:
            throughput = len(all_advance) / wall_run
            print(f"Throughput: {throughput:.1f} advances/sec")

        # RSS
        try:
            ps_out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(daemon.pid)], text=True,
            ).strip()
            if ps_out:
                print(f"\nDaemon RSS: {int(ps_out) / 1024:.0f} MB")
        except Exception:
            pass

        # === Phase 3: Reset latency (destroy + recreate) ===
        print(f"\n--- Phase 3: Reset latency (destroy + create, 4 samples serial) ---")
        reset_latencies = []
        for i in range(4):
            t0 = time.monotonic()
            sid_new, create_ms = create_session_timed(stub, 1000 + i)
            reset_ms = (time.monotonic() - t0) * 1000
            destroy_session_timed(stub, sid_new)
            reset_latencies.append(reset_ms)
            print(f"  Reset {i+1}: {reset_ms:.0f}ms")
        print(f"Reset latency: {fmt_stats(reset_latencies)}")

        return 0 if failed == 0 else 1

    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.kill()
        print("\nDaemon stopped.")


if __name__ == "__main__":
    sys.exit(main())
