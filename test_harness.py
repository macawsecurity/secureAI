#!/usr/bin/env python3
"""
MACAW Adapters Test Harness

Tests all examples in secureAI/examples/.

Usage:
    # Quick mode - use current Python environment (after pip install)
    python3 test_harness.py

    # Full integration test - extracts SDK and creates fresh venv
    python3 test_harness.py --sdk-zip ~/Downloads/macaw-client-*.zip

Options:
    --sdk-zip         Path to SDK zip file (optional - enables full integration test)
    --openai-key      OpenAI API key for OpenAI/LangChain examples
    --anthropic-key   Anthropic API key for Anthropic/LangChain examples
    --install-local   Install macaw-adapters from local dist/ instead of PyPI
    --verbose         Show full output from each test
"""

import os
import sys
import subprocess
import zipfile
import time
import signal
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict
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


class TestHarness:
    def __init__(
        self,
        examples_dir: Path,
        sdk_zip: Optional[Path] = None,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        install_local: bool = False,
        verbose: bool = False,
    ):
        self.examples_dir = examples_dir
        self.sdk_zip = sdk_zip
        self.openai_key = openai_key
        self.anthropic_key = anthropic_key
        self.install_local = install_local
        self.verbose = verbose
        self.quick_mode = sdk_zip is None

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.harness_dir = Path(f"/tmp/macaw-harness-{self.timestamp}")
        self.venv_dir = self.harness_dir / "venv"
        self.sdk_dir = self.harness_dir / "sdk"
        self.results_dir = self.harness_dir / "results"
        self.test_cases: List[TestCase] = []

        # In quick mode, use current Python interpreter
        if self.quick_mode:
            self.python = Path(sys.executable)
            self.macaw_config_dir = None

    def setup(self):
        """Create harness directory, extract SDK, and set up virtual environment."""
        print("=" * 60)
        print("MACAW Test Harness Setup")
        print("=" * 60)

        if self.quick_mode:
            print("\nQuick mode: Using current Python environment")
            print(f"Python: {self.python}")
            self.results_dir = Path(f"/tmp/macaw-harness-{self.timestamp}")
            self.results_dir.mkdir(parents=True, exist_ok=True)
            return

        print(f"\nHarness directory: {self.harness_dir}")

        # Create directories
        self.harness_dir.mkdir(parents=True, exist_ok=True)
        self.sdk_dir.mkdir(exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)

        # Extract SDK zip
        print(f"\n1. Extracting SDK from: {self.sdk_zip.name}")
        with zipfile.ZipFile(self.sdk_zip, 'r') as zf:
            zf.extractall(self.sdk_dir)

        # Find the wheel file matching current platform
        wheels = list(self.sdk_dir.rglob("macaw_client-*.whl"))
        if not wheels:
            raise FileNotFoundError(f"No macaw_client wheel found in {self.sdk_zip}")

        # Select wheel matching current Python version and platform
        py_version = f"cp{sys.version_info.major}{sys.version_info.minor}"

        # Determine platform tag
        import platform
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "darwin":
            if machine == "arm64":
                platform_tag = "macosx_11_0_arm64"
            else:
                platform_tag = "macosx_10_9_x86_64"
        elif system == "linux":
            platform_tag = "manylinux_2_17_x86_64"
        elif system == "windows":
            platform_tag = "win_amd64"
        else:
            platform_tag = None

        # Find matching wheel
        self.wheel_path = None
        for wheel in wheels:
            wheel_name = wheel.name
            if py_version in wheel_name and (platform_tag is None or platform_tag in wheel_name):
                self.wheel_path = wheel
                break

        if not self.wheel_path:
            # Fall back to any wheel with matching Python version
            for wheel in wheels:
                if py_version in wheel.name:
                    self.wheel_path = wheel
                    print(f"   Warning: No exact platform match, using: {wheel.name}")
                    break

        if not self.wheel_path:
            raise FileNotFoundError(f"No matching wheel found for {py_version} on {platform_tag}")

        print(f"   Found wheel: {self.wheel_path.name}")

        # Find .macaw config directory
        macaw_configs = list(self.sdk_dir.rglob(".macaw"))
        if macaw_configs:
            self.macaw_config_dir = macaw_configs[0]
            print(f"   Found config: {self.macaw_config_dir}")
        else:
            self.macaw_config_dir = None
            print("   Warning: No .macaw config directory found in SDK")

        # Create virtual environment
        print(f"\n2. Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(self.venv_dir)], check=True)

        # Get pip path
        self.pip = self.venv_dir / "bin" / "pip"
        self.python = self.venv_dir / "bin" / "python"

        # Upgrade pip
        subprocess.run(
            [str(self.pip), "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
        )

        # Install macaw-client from SDK
        print(f"\n3. Installing macaw-client from SDK...")
        result = subprocess.run(
            [str(self.pip), "install", str(self.wheel_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"   Error: {result.stderr}")
            raise RuntimeError("Failed to install macaw-client")
        print(f"   Installed: {self.wheel_path.name}")

        # Install macaw-adapters
        print(f"\n4. Installing macaw-adapters...")
        if self.install_local:
            dist_dir = self.examples_dir.parent / "dist"
            local_wheels = list(dist_dir.glob("macaw_adapters-*.whl"))
            if local_wheels:
                install_target = str(local_wheels[-1]) + "[all]"
                print(f"   From local: {local_wheels[-1].name}")
            else:
                print("   No local wheel found, falling back to PyPI")
                install_target = "macaw-adapters[all]"
        else:
            install_target = "macaw-adapters[all]"
            print("   From PyPI")

        result = subprocess.run(
            [str(self.pip), "install", "--force-reinstall", "--no-cache-dir", install_target],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"   Error: {result.stderr}")
            raise RuntimeError("Failed to install macaw-adapters")
        print("   Installed successfully")

        # Show API key status
        print(f"\n5. API Keys:")
        print(f"   OpenAI:    {'configured' if self.openai_key else 'not provided'}")
        print(f"   Anthropic: {'configured' if self.anthropic_key else 'not provided'}")

        print(f"\nSetup complete!")
        print("=" * 60)

    def discover_tests(self):
        """Discover all test cases from examples directory."""
        print("\nDiscovering test cases...")

        # Define test configurations
        test_configs = {
            # OpenAI examples
            "openai/openai_1a_dropin_simple.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "openai/openai_1b_multiuser_bind.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "openai/openai_1b_multiuser_bind_streaming.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "openai/openai_1c_a2a_invoke.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            # Anthropic examples
            "anthropic/anthropic_1a_dropin_simple.py": {
                "requires_keys": ["ANTHROPIC_API_KEY"],
            },
            "anthropic/anthropic_1b_multiuser_bind.py": {
                "requires_keys": ["ANTHROPIC_API_KEY"],
            },
            "anthropic/anthropic_1b_multiuser_bind_streaming.py": {
                "requires_keys": ["ANTHROPIC_API_KEY"],
            },
            "anthropic/anthropic_1c_a2a_invoke.py": {
                "requires_keys": ["ANTHROPIC_API_KEY"],
            },
            # LangChain examples
            "langchain/langchain_1a_dropin_simple.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "langchain/langchain_1b_multiuser.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "langchain/langchain_1c_orchestration.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "langchain/langchain_1d_llm_openai.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            "langchain/langchain_1e_llm_anthropic.py": {
                "requires_keys": ["ANTHROPIC_API_KEY"],
            },
            "langchain/langchain_1f_memory.py": {
                "requires_keys": ["OPENAI_API_KEY"],
            },
            # MCP examples - server/client pairs
            "mcp/1a_simple_invocation.py": {
                "requires_server": "mcp/securemcp_calculator.py",
                "timeout": 90,
            },
            "mcp/1b_discovery_and_resources.py": {
                "requires_server": "mcp/securemcp_calculator.py",
                "timeout": 90,
            },
            "mcp/1c_logging_client.py": {
                "requires_server": "mcp/securemcp_calculator.py",
                "timeout": 90,
            },
            "mcp/1d_progress_client.py": {
                "requires_server": "mcp/securemcp_calculator.py",
                "timeout": 90,
            },
            "mcp/1e_sampling_client.py": {
                "requires_server": "mcp/1e_sampling_server.py",
                "timeout": 90,
            },
            "mcp/1f_elicitation_client.py": {
                "requires_server": "mcp/1f_elicitation_server.py",
                "timeout": 90,
            },
            "mcp/1g_roots_client.py": {
                "requires_server": "mcp/1g_roots_server.py",
                "timeout": 90,
            },
        }

        for script_rel, config in test_configs.items():
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

        print(f"Found {len(self.test_cases)} test cases:")
        for cat in ["openai", "anthropic", "langchain", "mcp"]:
            count = len([t for t in self.test_cases if t.category == cat])
            print(f"  {cat}: {count}")

    def _check_keys(self, test: TestCase) -> tuple[bool, list]:
        """Check if required API keys are available (from args or environment)."""
        missing = []
        for key in test.requires_keys:
            # Check command line args first, then environment
            if key == "OPENAI_API_KEY" and not (self.openai_key or os.environ.get("OPENAI_API_KEY")):
                missing.append(key)
            elif key == "ANTHROPIC_API_KEY" and not (self.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")):
                missing.append(key)
        return len(missing) == 0, missing

    def _get_env(self, test: TestCase) -> dict:
        """Build environment variables for test execution."""
        env = os.environ.copy()

        # Set PYTHONPATH to include examples parent (secureAI)
        env["PYTHONPATH"] = str(self.examples_dir.parent)

        # Set MACAW config directory
        if self.macaw_config_dir:
            env["MACAW_CONFIG_DIR"] = str(self.macaw_config_dir)

        # Set API keys
        if self.openai_key:
            env["OPENAI_API_KEY"] = self.openai_key
        if self.anthropic_key:
            env["ANTHROPIC_API_KEY"] = self.anthropic_key

        return env

    def run_test(self, test: TestCase) -> TestCase:
        """Run a single test case."""
        print(f"\n  {test.name}")

        # Check for required keys
        has_keys, missing = self._check_keys(test)
        if not has_keys:
            test.result = TestResult.SKIP
            test.error = f"Missing: {', '.join(missing)}"
            print(f"    SKIP - {test.error}")
            return test

        env = self._get_env(test)
        start_time = time.time()
        server_proc = None

        try:
            # Start server if needed
            if test.requires_server:
                print(f"    Starting server: {test.requires_server.name}")
                server_proc = subprocess.Popen(
                    [str(self.python), str(test.requires_server)],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid,
                )
                time.sleep(10)  # Wait for server to register with control plane

                if server_proc.poll() is not None:
                    test.result = TestResult.FAIL
                    test.error = "Server failed to start"
                    print(f"    FAIL - Server failed to start")
                    return test

            # Run the test script
            result = subprocess.run(
                [str(self.python), str(test.script)],
                env=env,
                capture_output=True,
                timeout=test.timeout,
            )

            test.duration = time.time() - start_time
            test.output = result.stdout.decode()
            test.error = result.stderr.decode()

            if result.returncode == 0:
                test.result = TestResult.PASS
                print(f"    PASS ({test.duration:.1f}s)")
            else:
                test.result = TestResult.FAIL
                print(f"    FAIL (exit code {result.returncode})")
                if self.verbose:
                    if test.output:
                        print(f"    stdout: {test.output[:300]}")
                    if test.error:
                        print(f"    stderr: {test.error[:300]}")

        except subprocess.TimeoutExpired:
            test.duration = time.time() - start_time
            test.result = TestResult.TIMEOUT
            print(f"    TIMEOUT after {test.timeout}s")

        except Exception as e:
            test.duration = time.time() - start_time
            test.result = TestResult.FAIL
            test.error = str(e)
            print(f"    FAIL - {e}")

        finally:
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
        """Run all discovered test cases."""
        print("\n" + "=" * 60)
        print("Running Tests")
        print("=" * 60)

        for category in ["openai", "anthropic", "langchain", "mcp"]:
            tests = [t for t in self.test_cases if t.category == category]
            if tests:
                print(f"\n{category.upper()} ({len(tests)} tests)")
                print("-" * 40)
                for test in tests:
                    self.run_test(test)

    def generate_report(self):
        """Generate test results report."""
        print("\n" + "=" * 60)
        print("Test Results Summary")
        print("=" * 60)

        # Summary by category
        categories = {}
        for test in self.test_cases:
            if test.category not in categories:
                categories[test.category] = {"pass": 0, "fail": 0, "skip": 0, "timeout": 0}

            if test.result == TestResult.PASS:
                categories[test.category]["pass"] += 1
            elif test.result == TestResult.FAIL:
                categories[test.category]["fail"] += 1
            elif test.result == TestResult.SKIP:
                categories[test.category]["skip"] += 1
            elif test.result == TestResult.TIMEOUT:
                categories[test.category]["timeout"] += 1

        for cat, stats in categories.items():
            total = sum(stats.values())
            passed = stats['pass']
            print(f"\n{cat.upper()}: {passed}/{total} passed", end="")
            if stats['fail']:
                print(f", {stats['fail']} failed", end="")
            if stats['skip']:
                print(f", {stats['skip']} skipped", end="")
            if stats['timeout']:
                print(f", {stats['timeout']} timeout", end="")
            print()

        # Overall
        total_pass = sum(c["pass"] for c in categories.values())
        total_fail = sum(c["fail"] for c in categories.values())
        total_skip = sum(c["skip"] for c in categories.values())
        total_timeout = sum(c["timeout"] for c in categories.values())
        total = len(self.test_cases)

        print(f"\n{'=' * 40}")
        print(f"OVERALL: {total_pass}/{total} passed")
        if total_fail:
            print(f"  Failed:  {total_fail}")
        if total_skip:
            print(f"  Skipped: {total_skip}")
        if total_timeout:
            print(f"  Timeout: {total_timeout}")

        # Write detailed results
        results_file = self.results_dir / "results.txt"
        with open(results_file, "w") as f:
            f.write(f"MACAW Adapters Test Results\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Harness:   {self.harness_dir}\n")
            f.write(f"SDK:       {self.sdk_zip.name if self.sdk_zip else 'quick mode (current environment)'}\n")
            f.write(f"OpenAI:    {'yes' if self.openai_key else 'no'}\n")
            f.write(f"Anthropic: {'yes' if self.anthropic_key else 'no'}\n")
            f.write(f"{'=' * 60}\n\n")

            for test in self.test_cases:
                f.write(f"Test: {test.name}\n")
                f.write(f"Result: {test.result.value}\n")
                f.write(f"Duration: {test.duration:.1f}s\n")
                if test.error and test.result != TestResult.PASS:
                    f.write(f"Error: {test.error}\n")
                f.write("-" * 40 + "\n")
                if test.output and self.verbose:
                    f.write("Output:\n")
                    f.write(test.output)
                f.write("\n")

        print(f"\nDetailed results: {results_file}")
        print(f"Harness directory: {self.harness_dir}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MACAW Adapters Test Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick mode - use current environment (after pip install)
  python3 test_harness.py

  # Full integration test - extracts SDK zip and creates fresh venv
  python3 test_harness.py --sdk-zip ~/Downloads/macaw-client-*.zip

  # With API keys for LLM tests
  python3 test_harness.py --openai-key sk-proj-... --anthropic-key sk-ant-...

  # MCP tests only (no API keys needed)
  python3 test_harness.py
""",
    )
    parser.add_argument(
        "--sdk-zip",
        type=Path,
        help="Path to SDK zip file (optional - enables full integration test mode)",
    )
    parser.add_argument(
        "--openai-key",
        type=str,
        help="OpenAI API key",
    )
    parser.add_argument(
        "--anthropic-key",
        type=str,
        help="Anthropic API key",
    )
    parser.add_argument(
        "--install-local",
        action="store_true",
        help="Install macaw-adapters from local dist/ instead of PyPI",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )

    args = parser.parse_args()

    # Validate SDK zip exists (if provided)
    if args.sdk_zip and not args.sdk_zip.exists():
        print(f"Error: SDK zip not found: {args.sdk_zip}")
        sys.exit(1)

    # Find examples directory
    script_dir = Path(__file__).parent
    examples_dir = script_dir / "examples"

    if not examples_dir.exists():
        print(f"Error: Examples directory not found: {examples_dir}")
        sys.exit(1)

    # Quick mode info
    if not args.sdk_zip:
        print("Running in quick mode (using current Python environment)")
        print("For full integration test, use: --sdk-zip path/to/macaw-client-*.zip")
        print()

    harness = TestHarness(
        examples_dir=examples_dir,
        sdk_zip=args.sdk_zip,
        openai_key=args.openai_key,
        anthropic_key=args.anthropic_key,
        install_local=args.install_local,
        verbose=args.verbose,
    )

    try:
        harness.setup()
        harness.discover_tests()
        harness.run_all()
        harness.generate_report()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
