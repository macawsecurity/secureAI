#!/usr/bin/env python3
"""
MACAW Quick Test Harness

Runs MCP + 1a examples only. No Identity Provider required.
For full test suite (including multi-user examples), use test_harness.py

Usage:
    python3 test_harness_quick.py
    python3 test_harness_quick.py --verbose

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY and/or ANTHROPIC_API_KEY for LLM examples
    - MCP examples run without any API keys
"""

import os
import sys
import subprocess
import time
import signal
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    TIMEOUT = "TIMEOUT"


@dataclass
class TestCase:
    name: str
    script: Path
    category: str
    requires_server: Optional[Path] = None
    requires_keys: List[str] = field(default_factory=list)
    timeout: int = 60
    result: TestResult = TestResult.SKIP
    output: str = ""
    error: str = ""
    duration: float = 0


# Quick tests - no IdP required
QUICK_TESTS = {
    # MCP examples - no API keys needed, just MACAW
    "mcp/1a_simple_invocation.py": {
        "requires_server": "mcp/securemcp_calculator.py",
        "timeout": 60,
    },
    "mcp/1b_discovery_and_resources.py": {
        "requires_server": "mcp/securemcp_calculator.py",
        "timeout": 60,
    },
    "mcp/1c_logging_client.py": {
        "requires_server": "mcp/securemcp_calculator.py",
        "timeout": 60,
    },
    "mcp/1d_progress_client.py": {
        "requires_server": "mcp/securemcp_calculator.py",
        "timeout": 60,
    },
    "mcp/1e_sampling_client.py": {
        "requires_server": "mcp/1e_sampling_server.py",
        "timeout": 60,
    },
    "mcp/1g_roots_client.py": {
        "requires_server": "mcp/1g_roots_server.py",
        "timeout": 60,
    },
    # 1a examples - need API keys but no IdP
    "openai/openai_1a_dropin_simple.py": {
        "requires_keys": ["OPENAI_API_KEY"],
        "timeout": 30,
    },
    "anthropic/anthropic_1a_dropin_simple.py": {
        "requires_keys": ["ANTHROPIC_API_KEY"],
        "timeout": 30,
    },
    "langchain/langchain_1a_dropin_simple.py": {
        "requires_keys": ["OPENAI_API_KEY"],
        "timeout": 30,
    },
}


class QuickTestHarness:
    def __init__(self, examples_dir: Path, verbose: bool = False):
        self.examples_dir = examples_dir
        self.verbose = verbose
        self.python = Path(sys.executable)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_dir = Path(f"/tmp/macaw-quick-{self.timestamp}")
        self.test_cases: List[TestCase] = []

    def discover_tests(self):
        """Discover quick test cases."""
        for script_rel, config in QUICK_TESTS.items():
            script_path = self.examples_dir / script_rel
            if script_path.exists():
                category = script_rel.split("/")[0]
                server_path = None
                if config.get("requires_server"):
                    server_path = self.examples_dir / config["requires_server"]

                tc = TestCase(
                    name=script_rel,
                    script=script_path,
                    category=category,
                    requires_server=server_path,
                    requires_keys=config.get("requires_keys", []),
                    timeout=config.get("timeout", 60),
                )
                self.test_cases.append(tc)

    def _check_keys(self, test: TestCase) -> tuple:
        """Check if required API keys are available."""
        missing = []
        for key in test.requires_keys:
            if not os.environ.get(key):
                missing.append(key)
        return len(missing) == 0, missing

    def _get_env(self, test: TestCase) -> dict:
        """Build environment variables for test execution."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.examples_dir.parent)
        return env

    def run_test(self, test: TestCase) -> TestCase:
        """Run a single test case."""
        # Check for required keys
        has_keys, missing = self._check_keys(test)
        if not has_keys:
            test.result = TestResult.SKIP
            test.error = f"Missing: {', '.join(missing)}"
            return test

        env = self._get_env(test)
        start_time = time.time()
        server_proc = None

        try:
            # Start server if required
            if test.requires_server and test.requires_server.exists():
                server_proc = subprocess.Popen(
                    [str(self.python), str(test.requires_server)],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid,
                )
                time.sleep(2)  # Wait for server to start

                if server_proc.poll() is not None:
                    test.result = TestResult.FAIL
                    test.error = "Server failed to start"
                    return test

            # Run the test
            result = subprocess.run(
                [str(self.python), str(test.script)],
                env=env,
                capture_output=True,
                timeout=test.timeout,
            )

            test.duration = time.time() - start_time
            test.output = result.stdout.decode("utf-8", errors="replace")
            test.error = result.stderr.decode("utf-8", errors="replace")

            if result.returncode == 0:
                test.result = TestResult.PASS
            else:
                test.result = TestResult.FAIL

        except subprocess.TimeoutExpired:
            test.result = TestResult.TIMEOUT
            test.duration = test.timeout
            test.error = f"Timeout after {test.timeout}s"

        except Exception as e:
            test.result = TestResult.FAIL
            test.error = str(e)
            test.duration = time.time() - start_time

        finally:
            # Cleanup server
            if server_proc:
                try:
                    os.killpg(os.getpgid(server_proc.pid), signal.SIGTERM)
                    server_proc.wait(timeout=5)
                except Exception:
                    try:
                        os.killpg(os.getpgid(server_proc.pid), signal.SIGKILL)
                    except Exception:
                        pass

        return test

    def run_all(self):
        """Run all test cases."""
        self.results_dir.mkdir(parents=True, exist_ok=True)

        for category in ["mcp", "openai", "anthropic", "langchain"]:
            category_tests = [t for t in self.test_cases if t.category == category]
            if not category_tests:
                continue

            print(f"\n{category.upper()} ({len(category_tests)} tests)")
            print("-" * 40)

            for test in category_tests:
                self.run_test(test)
                status = test.result.value
                if test.result == TestResult.PASS:
                    print(f"  [PASS] {test.name} ({test.duration:.1f}s)")
                elif test.result == TestResult.SKIP:
                    print(f"  [SKIP] {test.name} - {test.error}")
                elif test.result == TestResult.TIMEOUT:
                    print(f"  [TIME] {test.name} - {test.error}")
                else:
                    print(f"  [FAIL] {test.name} ({test.duration:.1f}s)")
                    if self.verbose and test.error:
                        for line in test.error.strip().split("\n")[-5:]:
                            print(f"         {line}")

    def print_summary(self):
        """Print test summary."""
        passed = len([t for t in self.test_cases if t.result == TestResult.PASS])
        failed = len([t for t in self.test_cases if t.result == TestResult.FAIL])
        skipped = len([t for t in self.test_cases if t.result == TestResult.SKIP])
        timeout = len([t for t in self.test_cases if t.result == TestResult.TIMEOUT])
        total = len(self.test_cases)

        print("\n" + "=" * 60)
        print("QUICK TEST SUMMARY")
        print("=" * 60)
        print(f"  Passed:  {passed}/{total}")
        print(f"  Failed:  {failed}")
        print(f"  Skipped: {skipped}")
        print(f"  Timeout: {timeout}")
        print("=" * 60)

        if skipped > 0:
            print("\nSkipped tests need API keys:")
            print("  export OPENAI_API_KEY=sk-...")
            print("  export ANTHROPIC_API_KEY=sk-ant-...")

        if failed > 0 or timeout > 0:
            print("\nFor full output, run with --verbose")

        print(f"\nFor multi-user examples (requires IdP), run:")
        print(f"  python test_harness.py")


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Find examples directory
    script_dir = Path(__file__).parent
    examples_dir = script_dir / "examples"

    if not examples_dir.exists():
        print(f"Error: examples directory not found at {examples_dir}")
        sys.exit(1)

    print("=" * 60)
    print("MACAW Quick Test Harness")
    print("=" * 60)
    print(f"Examples: {examples_dir}")
    print(f"Python:   {sys.executable}")
    print(f"Tests:    MCP + 1a examples (no IdP required)")

    harness = QuickTestHarness(examples_dir, verbose=verbose)
    harness.discover_tests()

    print(f"\nFound {len(harness.test_cases)} quick tests")

    harness.run_all()
    harness.print_summary()

    # Exit with error if any tests failed
    failed = len([t for t in harness.test_cases if t.result == TestResult.FAIL])
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
