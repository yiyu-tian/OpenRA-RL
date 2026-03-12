#!/usr/bin/env python3
"""Stress test for multi-session OpenRA daemon.

Usage:
    python test_multi_session.py [num_sessions]

Default: 2 sessions. Try 2 → 8 → 16 → 64.
"""

import os
import subprocess
import sys
import time
import threading
import grpc

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

from openra_env.generated import rl_bridge_pb2, rl_bridge_pb2_grpc

OPENRA_DIR = os.path.join(os.path.dirname(__file__), "OpenRA")
GRPC_PORT = 9999
MAP_NAME = "singles.oramap"
BOTS = "Multi1:rl-agent,Multi0:beginner"

def start_daemon():
    """Start the multi-session OpenRA daemon."""
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
    print(f"Daemon started (PID={proc.pid})")
    return proc


def wait_for_daemon(channel, max_wait=30):
    """Wait for the gRPC server to be ready."""
    stub = rl_bridge_pb2_grpc.RLBridgeStub(channel)
    for i in range(max_wait):
        try:
            # Try a simple GetState — will fail but proves server is up
            stub.GetState(rl_bridge_pb2.StateRequest(), timeout=2.0)
            print(f"Daemon ready after {i+1}s")
            return True
        except grpc.RpcError:
            time.sleep(1)
    print("Daemon failed to start!")
    return False


def run_session(stub, session_id, session_num, results, ticks_per_step=50, num_steps=5):
    """Run a single session: create, advance a few ticks, destroy."""
    try:
        t0 = time.monotonic()

        # Wait for session to be ready (phase must be "playing")
        for attempt in range(60):
            try:
                state = stub.GetState(
                    rl_bridge_pb2.StateRequest(session_id=session_id),
                    timeout=5.0,
                )
                if state.phase == "playing":
                    break
            except grpc.RpcError:
                pass
            time.sleep(0.5)

        t_ready = time.monotonic() - t0
        print(f"  Session {session_num} ({session_id}): ready in {t_ready:.1f}s, phase={state.phase}")

        # Advance a few ticks
        for step in range(num_steps):
            obs = stub.FastAdvance(
                rl_bridge_pb2.FastAdvanceRequest(
                    ticks=ticks_per_step,
                    session_id=session_id,
                ),
                timeout=60.0,
            )
            if obs.done:
                print(f"  Session {session_num}: game ended at step {step}, result={obs.result}")
                break

        t_total = time.monotonic() - t0

        # Destroy session
        stub.DestroySession(
            rl_bridge_pb2.DestroySessionRequest(session_id=session_id),
            timeout=10.0,
        )

        results[session_num] = {
            "ok": True,
            "ready_time": t_ready,
            "total_time": t_total,
            "final_tick": obs.tick,
        }
        print(f"  Session {session_num} ({session_id}): done in {t_total:.1f}s, tick={obs.tick}")

    except Exception as e:
        results[session_num] = {"ok": False, "error": str(e)}
        print(f"  Session {session_num} ({session_id}): FAILED - {e}")


def main():
    num_sessions = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    print(f"=== Multi-session stress test: {num_sessions} sessions ===\n")

    # Start daemon
    daemon = start_daemon()

    try:
        # Connect
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

        # Create all sessions (wait for each to be ready before creating next)
        print(f"\nCreating {num_sessions} sessions...")
        t_create_start = time.monotonic()
        session_ids = []
        for i in range(num_sessions):
            resp = stub.CreateSession(
                rl_bridge_pb2.CreateSessionRequest(
                    map_name=MAP_NAME,
                    bots=BOTS,
                    seed=42 + i,
                ),
                timeout=30.0,
            )
            session_ids.append(resp.session_id)
            print(f"  Created session {i}: {resp.session_id}")
            # Wait for session to be ready before creating next one
            for _ in range(60):
                state = stub.GetState(
                    rl_bridge_pb2.StateRequest(session_id=resp.session_id),
                    timeout=5.0,
                )
                if state.phase == "playing":
                    break
                time.sleep(0.5)
            print(f"    Ready: phase={state.phase}")

        t_create = time.monotonic() - t_create_start
        print(f"All {num_sessions} sessions created in {t_create:.1f}s\n")

        # Run sessions concurrently
        print(f"Running {num_sessions} sessions concurrently...")
        results = {}
        threads = []
        t_run_start = time.monotonic()

        for i, sid in enumerate(session_ids):
            t = threading.Thread(target=run_session, args=(stub, sid, i, results))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=120)

        t_run = time.monotonic() - t_run_start

        # Summary
        print(f"\n=== Results ===")
        ok = sum(1 for r in results.values() if r.get("ok"))
        failed = num_sessions - ok
        ready_times = [r["ready_time"] for r in results.values() if r.get("ok")]
        total_times = [r["total_time"] for r in results.values() if r.get("ok")]

        print(f"Sessions: {ok}/{num_sessions} OK, {failed} failed")
        if ready_times:
            print(f"Ready time: min={min(ready_times):.1f}s, max={max(ready_times):.1f}s, avg={sum(ready_times)/len(ready_times):.1f}s")
        if total_times:
            print(f"Total time: min={min(total_times):.1f}s, max={max(total_times):.1f}s, avg={sum(total_times)/len(total_times):.1f}s")
        print(f"Wall clock: create={t_create:.1f}s, run={t_run:.1f}s")

        # Check daemon memory
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            print(f"Daemon peak RSS: {rss / 1024:.0f} MB")
        except Exception:
            pass

        # Check daemon process RSS via ps
        try:
            ps_out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(daemon.pid)],
                text=True,
            ).strip()
            if ps_out:
                print(f"Daemon current RSS: {int(ps_out) / 1024:.0f} MB")
        except Exception:
            pass

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
