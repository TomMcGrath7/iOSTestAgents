"""Tests for the CLI."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from iostestagents.cli import app

runner = CliRunner()


class TestDoctorCommand:
    @patch("iostestagents.cli.XcodeBuildMCPDevice")
    @patch("iostestagents.cli.BridgeDevice")
    @patch("urllib.request.urlopen", side_effect=Exception("no ollama"))
    @patch("subprocess.run")
    def test_doctor_all_pass(self, mock_run, mock_urlopen, mock_bridge_cls, mock_mcp_cls):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"devices": {"runtime": [{"name": "iPhone", "isAvailable": True}]}}),
            stderr="",
        )
        mock_bridge_cls.is_available.return_value = True
        mock_bridge_cls.is_running.return_value = False
        mock_mcp_cls.is_available.return_value = False
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    @patch("iostestagents.cli.XcodeBuildMCPDevice")
    @patch("iostestagents.cli.BridgeDevice")
    @patch("urllib.request.urlopen", side_effect=Exception("no ollama"))
    @patch("subprocess.run")
    def test_doctor_no_backends(self, mock_run, mock_urlopen, mock_bridge_cls, mock_mcp_cls):
        """No device backends available causes failure."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"devices": {"r": [{"name": "iPhone"}]}}),
            stderr="",
        )
        mock_bridge_cls.is_available.return_value = False
        mock_mcp_cls.is_available.return_value = False
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "No device backends available" in result.output

    @patch("iostestagents.cli.XcodeBuildMCPDevice")
    @patch("iostestagents.cli.BridgeDevice")
    @patch("urllib.request.urlopen", side_effect=Exception("no ollama"))
    @patch("subprocess.run")
    def test_doctor_no_providers(self, mock_run, mock_urlopen, mock_bridge_cls, mock_mcp_cls):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"devices": {"r": [{"name": "iPhone", "isAvailable": True}]}}),
            stderr="",
        )
        mock_bridge_cls.is_available.return_value = True
        mock_bridge_cls.is_running.return_value = False
        mock_mcp_cls.is_available.return_value = False
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "No LLM providers available" in result.output


class TestRunCommand:
    def test_run_missing_required_options(self):
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    @patch("iostestagents.agent.loop.run_agent")  # patch where it's used, not where it's defined
    def test_run_success(self, mock_run_agent, tmp_path):
        from iostestagents.agent.models import RunResult, TokenUsage

        mock_run_agent.return_value = RunResult(
            run_id="test123",
            goal="test",
            device="iPhone 16",
            status="success",
            message="Done",
            total_tokens=TokenUsage(input_tokens=100, output_tokens=50),
            estimated_cost=0.001,
        )
        result = runner.invoke(
            app,
            [
                "run",
                "--device",
                "iPhone 16",
                "--app",
                "com.test",
                "--goal",
                "test goal",
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "success" in result.output.lower() or "Done" in result.output

    @patch("iostestagents.agent.loop.run_agent")
    def test_run_failure_exit_code(self, mock_run_agent, tmp_path):
        from iostestagents.agent.models import RunResult, TokenUsage

        mock_run_agent.return_value = RunResult(
            run_id="fail123",
            goal="test",
            device="iPhone 16",
            status="failure",
            message="Could not complete",
            total_tokens=TokenUsage(input_tokens=100, output_tokens=50),
            estimated_cost=0.001,
        )
        result = runner.invoke(
            app,
            [
                "run",
                "--device",
                "iPhone 16",
                "--app",
                "com.test",
                "--goal",
                "test goal",
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
