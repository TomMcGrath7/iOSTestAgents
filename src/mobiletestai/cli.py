"""CLI for mobiletestai — AI-powered iOS app testing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from mobiletestai.device.bridge import BridgeDevice
from mobiletestai.device.xcodebuildmcp import XcodeBuildMCPDevice
from mobiletestai.util.logging import setup_logging

app = typer.Typer(
    name="mobiletestai",
    help="AI-powered iOS app testing framework",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    device: str = typer.Option(..., "--device", "-d", help="Simulator device name"),
    app_bundle: str = typer.Option(..., "--app", "-a", help="App bundle identifier"),
    goal: str = typer.Option(..., "--goal", "-g", help="Natural language test goal"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum agent steps"),
    model: Optional[str] = typer.Option(None, "--model", help="LLM model to use (default per provider)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="LLM provider: anthropic, openai, ollama (auto-detect if omitted)"),
    output: str = typer.Option("output", "--output", "-o", help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    step_delay: float = typer.Option(1.5, "--step-delay", help="Delay between steps (seconds)"),
    record: bool = typer.Option(False, "--record", help="Record screen video"),
    no_reset: bool = typer.Option(False, "--no-reset", help="Skip app reset before run"),
    app_path: Optional[str] = typer.Option(None, "--app-path", help="Path to .app for reinstall"),
    backend: str = typer.Option("testbridge", "--backend", "-b", help="Device backend: testbridge or xcodebuildmcp"),
    no_vision: bool = typer.Option(False, "--no-vision", help="Skip sending screenshots to LLM (use accessibility tree only, faster)"),
    vision_model: Optional[str] = typer.Option(None, "--vision-model", help="Vision model for fallback when stuck (e.g. gemma3:4b, qwen3-vl)"),
) -> None:
    """Run an AI agent to test an iOS app with a natural language goal."""
    setup_logging(verbose)

    from mobiletestai.agent.loop import run_agent
    from mobiletestai.device.simulator import SimulatorManager

    # Resolve backend instance
    backend_instance = None
    if backend == "xcodebuildmcp":
        sim = SimulatorManager()
        dev = sim.find_device(device)
        backend_instance = XcodeBuildMCPDevice(dev.udid, bundle_id=app_bundle)
    elif backend == "testbridge":
        pass  # run_agent defaults to BridgeDevice
    else:
        console.print(f"[red]Unknown backend: {backend}. Use 'testbridge' or 'xcodebuildmcp'.[/red]")
        raise typer.Exit(code=1)

    result = run_agent(
        goal=goal,
        device_name=device,
        bundle_id=app_bundle,
        max_steps=max_steps,
        model=model,
        vision_model=vision_model,
        provider=provider,
        output_dir=output,
        step_delay=step_delay,
        record=record,
        reset=not no_reset,
        app_path=app_path,
        backend=backend_instance,
        vision=not no_vision,
    )

    # Print summary
    console.print()
    table = Table(title="Run Summary")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Run ID", result.run_id)
    table.add_row("Goal", result.goal)
    table.add_row("Device", result.device)
    table.add_row("Status", result.status)
    table.add_row("Steps", str(len(result.steps)))
    table.add_row("Message", result.message)
    table.add_row(
        "Tokens",
        f"{result.total_tokens.input_tokens:,} in / {result.total_tokens.output_tokens:,} out",
    )
    table.add_row("Est. Cost", f"${result.estimated_cost:.4f}")
    console.print(table)

    # Save result JSON
    result_path = Path(output) / f"{result.run_id}_result.json"
    result_path.write_text(result.model_dump_json(indent=2))
    console.print(f"\nResults saved to {result_path}")

    if result.status != "success":
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Check that all dependencies are available."""
    setup_logging(False)
    all_ok = True

    def _check(name: str, cmd: list[str]) -> bool:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            ok = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            ok = False
        status = "[green]OK[/green]" if ok else "[red]MISSING[/red]"
        console.print(f"  {name}: {status}")
        return ok

    console.print("[bold]Checking dependencies...[/bold]")
    all_ok &= _check("xcrun simctl", ["xcrun", "simctl", "list", "devices", "-j"])

    # Check device backends — at least one must be available
    console.print("\n[bold]Checking device backends...[/bold]")
    any_backend = False

    if XcodeBuildMCPDevice.is_available():
        console.print("  XcodeBuildMCP:      [green]OK[/green]")
        any_backend = True
    else:
        console.print("  XcodeBuildMCP:      [dim]Not installed (npm install -g xcodebuildmcp@latest)[/dim]")

    if BridgeDevice.is_available():
        console.print("  TestBridge project: [green]OK[/green]")
        any_backend = True
        if BridgeDevice.is_running():
            console.print("  TestBridge server:  [green]Running[/green]")
        else:
            console.print("  TestBridge server:  [dim]Not running (starts automatically during test runs)[/dim]")
    else:
        console.print("  TestBridge project: [dim]Not found (testbridge/TestBridge.xcodeproj)[/dim]")

    if not any_backend:
        console.print("  [red]No device backends available. Install XcodeBuildMCP or build TestBridge.[/red]")
        all_ok = False

    # Check for simulators
    console.print("\n[bold]Checking simulators...[/bold]")
    try:
        raw = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available", "-j"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(raw.stdout)
        device_count = sum(
            len(devs) for devs in data.get("devices", {}).values()
        )
        if device_count > 0:
            console.print(f"  Simulators: [green]{device_count} available[/green]")
        else:
            console.print("  Simulators: [red]None available[/red]")
            all_ok = False
    except Exception:
        console.print("  Simulators: [red]Could not list[/red]")
        all_ok = False

    # Check LLM providers
    console.print("\n[bold]Checking LLM providers...[/bold]")
    any_provider = False
    if os.environ.get("ANTHROPIC_API_KEY"):
        console.print("  Anthropic: [green]ANTHROPIC_API_KEY set[/green]")
        any_provider = True
    else:
        console.print("  Anthropic: [dim]ANTHROPIC_API_KEY not set[/dim]")
    if os.environ.get("OPENAI_API_KEY"):
        console.print("  OpenAI:    [green]OPENAI_API_KEY set[/green]")
        any_provider = True
    else:
        console.print("  OpenAI:    [dim]OPENAI_API_KEY not set[/dim]")
    # Check Ollama
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/version", method="GET")
        with urllib.request.urlopen(req, timeout=2):
            console.print("  Ollama:    [green]Running locally[/green]")
            any_provider = True
    except Exception:
        console.print("  Ollama:    [dim]Not running[/dim]")

    if not any_provider:
        console.print("  [red]No LLM providers available[/red]")
        all_ok = False

    console.print()
    if all_ok:
        console.print("[bold green]All checks passed![/bold green]")
    else:
        console.print("[bold red]Some checks failed. See above.[/bold red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
