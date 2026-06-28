"""
SETUP INSTRUCTIONS FOR RUST-DEBUG (Phases 2-3)

This file contains setup instructions that Claude should execute when
the debug-suite skill is first used with Rust code.

Claude can run these commands to install rustc and clippy.
"""

SETUP_INSTRUCTIONS = """
===============================================================================
Debug-Suite v2.0: Rust-Debug (Phases 2-3) - Setup Instructions
===============================================================================

The Rust-Debug components (Phases 2-3) require the Rust toolchain.

OPTION 1: Quick Install (Recommended)
--------------------------------------
Run this command:

    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

Then add Rust to your PATH:

    source $HOME/.cargo/env

Verify installation:

    rustc --version
    cargo --version
    cargo clippy --version

OPTION 2: Using Package Manager (Linux/macOS)
----------------------------------------------

Ubuntu/Debian:
    sudo apt-get update
    sudo apt-get install rustc cargo clippy

macOS (Homebrew):
    brew install rust

Fedora/RHEL:
    sudo dnf install rust cargo clippy

OPTION 3: Docker (No Local Install)
------------------------------------
If you want to use Rust without installing locally:

    docker run -it rust:latest bash
    # Then use rust-debug inside container

Installation Verification
--------------------------
After installation, verify all components:

    $ rustc --version
    rustc 1.70.0 (90c541806 2023-05-31)

    $ cargo --version
    cargo 1.70.0 (ec8d8dafb 2023-04-25)

    $ cargo clippy --version
    clippy 0.1.70 (90c5418 2023-05-31)

If any of these fail, please reinstall.

Why These Tools?
----------------
- rustc: Rust compiler (includes borrow checker)
  → Phase 2 uses rustc's JSON output to detect lifetime violations

- clippy: Rust linter
  → Phase 3 uses clippy's warnings for style/performance/safety issues

- cargo: Package manager (required by clippy)
  → Clippy runs through cargo in a test project

What Happens If Tools Aren't Installed?
----------------------------------------
The skill will gracefully degrade:
- BorrowCheckerParser.rustc_available = False
  → Returns empty errors (no phase 2 analysis)

- ClippyLinter.clippy_available = False
  → Returns empty patterns (no phase 3 lints)

The full 4-phase pipeline still works; Phases 2-3 are skipped.

===============================================================================
"""

CLAUDE_INSTRUCTION = """
===== INSTRUCTION FOR CLAUDE =====

When this skill is loaded and Rust-Debug is first used:

1. Check if rustc and clippy are available:
   ```bash
   rustc --version && cargo clippy --version
   ```

2. If either fails, suggest to the user:
   "Rust-Debug requires rustc and clippy. Install using:
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env"

3. Once installed, Rust-Debug will automatically:
   - Parse borrow checker violations (Phase 2)
   - Run clippy for lint warnings (Phase 3)
   - Merge results into a unified report

4. If tools can't be installed:
   - PyProver can still provide formal verification (Phase 1)
   - Basic pattern detection still works (via static analysis)

===== END CLAUDE INSTRUCTION =====
"""

# This will be read by skill setup
REQUIRED_TOOLS = [
    {
        "name": "rustc",
        "command": "rustc --version",
        "install": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && source $HOME/.cargo/env",
        "description": "Rust compiler with borrow checker",
        "phase": "2",
    },
    {
        "name": "clippy",
        "command": "cargo clippy --version",
        "install": "rustup component add clippy",
        "description": "Rust linter for style/performance/safety",
        "phase": "3",
    },
]


def print_setup_guide():
    """Print setup guide for users/Claude."""
    print(SETUP_INSTRUCTIONS)


def claude_check_and_install():
    """
    Claude can call this to check for tools and prompt for installation.
    
    Returns:
        dict with 'rustc_available', 'clippy_available', 'all_available'
    """
    import subprocess
    
    status = {
        "rustc_available": False,
        "clippy_available": False,
    }
    
    # Check rustc
    try:
        subprocess.run(
            ["rustc", "--version"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        status["rustc_available"] = True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    
    # Check clippy
    try:
        subprocess.run(
            ["cargo", "clippy", "--version"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        status["clippy_available"] = True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    
    status["all_available"] = status["rustc_available"] and status["clippy_available"]
    
    # If missing, print instructions
    if not status["all_available"]:
        print("\n" + "="*80)
        print("RUST-DEBUG SETUP REQUIRED")
        print("="*80)
        if not status["rustc_available"]:
            print("❌ rustc not found. Install Rust toolchain:")
            print("   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y")
            print("   source $HOME/.cargo/env")
        if not status["clippy_available"]:
            print("❌ clippy not found. Install clippy:")
            print("   rustup component add clippy")
        print("="*80 + "\n")
    
    return status


if __name__ == "__main__":
    # When run directly, print setup guide
    print_setup_guide()
    
    # Check current status
    status = claude_check_and_install()
    print("\n" + "="*80)
    print("CURRENT STATUS:")
    print(f"  rustc:   {'✅ INSTALLED' if status['rustc_available'] else '❌ NOT FOUND'}")
    print(f"  clippy:  {'✅ INSTALLED' if status['clippy_available'] else '❌ NOT FOUND'}")
    print("="*80)
