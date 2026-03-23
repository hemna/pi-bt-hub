"""Systemd service management via subprocess calls."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ServiceStatus(BaseModel):
    """Status of a systemd service."""

    state: Literal["active", "inactive", "failed", "not-found", "unknown"]
    sub_state: str | None = None
    enabled: bool | None = None
    description: str | None = None


class ServiceResult(BaseModel):
    """Result of a service control operation."""

    success: bool
    message: str
    exit_code: int


class InstallResult(BaseModel):
    """Result of an install operation."""

    success: bool
    message: str
    output: str
    exit_code: int


class SystemdService:
    """Manage a systemd service via subprocess calls.

    Requires sudoers configuration to allow passwordless execution of
    systemctl and journalctl commands for the target service.
    """

    def __init__(self, service_name: str = "bt-bridge.service") -> None:
        self.service_name = service_name
        self._systemctl = shutil.which("systemctl") or "/bin/systemctl"
        self._journalctl = shutil.which("journalctl") or "/bin/journalctl"

    async def _run_command(self, *args: str, timeout: float = 10.0) -> tuple[int, str, str]:
        """Run a command and return (exit_code, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )
        except asyncio.TimeoutError:
            logger.warning("Command timed out: %s", " ".join(args))
            return (-1, "", "Command timed out")
        except Exception as e:
            logger.warning("Command failed: %s - %s", " ".join(args), e)
            return (-1, "", str(e))

    async def status(self) -> ServiceStatus:
        """Get the current status of the service."""
        # First check if the unit file exists using systemctl status
        # This is more reliable than is-active for detecting non-existent services
        _, _, status_err = await self._run_command(
            "sudo", self._systemctl, "status", self.service_name
        )

        if "could not be found" in status_err.lower() or "not found" in status_err.lower():
            return ServiceStatus(
                state="not-found",
                sub_state=None,
                enabled=None,
                description=None,
            )

        # Check if service is active
        exit_code, stdout, stderr = await self._run_command(
            "sudo", self._systemctl, "is-active", self.service_name
        )

        state: Literal["active", "inactive", "failed", "not-found", "unknown"]
        if exit_code == 0:
            state = "active"
        elif stdout == "inactive":
            state = "inactive"
        elif stdout == "failed":
            state = "failed"
        else:
            state = "unknown"

        # Get more details if service exists
        sub_state: str | None = None
        enabled: bool | None = None
        description: str | None = None

        if state != "not-found":
            # Get sub-state
            _, sub_stdout, _ = await self._run_command(
                "sudo", self._systemctl, "show", self.service_name, "--property=SubState", "--value"
            )
            if sub_stdout:
                sub_state = sub_stdout

            # Check if enabled
            en_code, en_stdout, _ = await self._run_command(
                "sudo", self._systemctl, "is-enabled", self.service_name
            )
            if en_stdout in ("enabled", "enabled-runtime"):
                enabled = True
            elif en_stdout in ("disabled", "masked"):
                enabled = False

            # Get description
            _, desc_stdout, _ = await self._run_command(
                "sudo",
                self._systemctl,
                "show",
                self.service_name,
                "--property=Description",
                "--value",
            )
            if desc_stdout:
                description = desc_stdout

        logger.debug(
            "Service %s status: state=%s sub_state=%s enabled=%s",
            self.service_name,
            state,
            sub_state,
            enabled,
        )

        return ServiceStatus(
            state=state,
            sub_state=sub_state,
            enabled=enabled,
            description=description,
        )

    async def start(self) -> ServiceResult:
        """Start the service."""
        logger.info("Starting service: %s", self.service_name)
        exit_code, stdout, stderr = await self._run_command(
            "sudo", self._systemctl, "start", self.service_name
        )

        if exit_code == 0:
            return ServiceResult(
                success=True,
                message=f"Service {self.service_name} started",
                exit_code=exit_code,
            )
        else:
            message = stderr or stdout or f"Failed to start {self.service_name}"
            if "permission denied" in message.lower():
                message = "Permission denied - check sudoers configuration"
            return ServiceResult(
                success=False,
                message=message,
                exit_code=exit_code,
            )

    async def stop(self) -> ServiceResult:
        """Stop the service."""
        logger.info("Stopping service: %s", self.service_name)
        exit_code, stdout, stderr = await self._run_command(
            "sudo", self._systemctl, "stop", self.service_name
        )

        if exit_code == 0:
            return ServiceResult(
                success=True,
                message=f"Service {self.service_name} stopped",
                exit_code=exit_code,
            )
        else:
            message = stderr or stdout or f"Failed to stop {self.service_name}"
            if "permission denied" in message.lower():
                message = "Permission denied - check sudoers configuration"
            return ServiceResult(
                success=False,
                message=message,
                exit_code=exit_code,
            )

    async def restart(self) -> ServiceResult:
        """Restart the service."""
        logger.info("Restarting service: %s", self.service_name)
        exit_code, stdout, stderr = await self._run_command(
            "sudo", self._systemctl, "restart", self.service_name
        )

        if exit_code == 0:
            return ServiceResult(
                success=True,
                message=f"Service {self.service_name} restarted",
                exit_code=exit_code,
            )
        else:
            message = stderr or stdout or f"Failed to restart {self.service_name}"
            if "permission denied" in message.lower():
                message = "Permission denied - check sudoers configuration"
            return ServiceResult(
                success=False,
                message=message,
                exit_code=exit_code,
            )

    async def logs(self, lines: int = 100) -> str:
        """Get recent journal logs for the service.

        Args:
            lines: Number of lines to retrieve (max 500).

        Returns:
            Log output as a string.
        """
        lines = min(max(lines, 1), 500)  # Clamp to 1-500

        logger.debug("Fetching %d log lines for %s", lines, self.service_name)
        exit_code, stdout, stderr = await self._run_command(
            "sudo",
            self._journalctl,
            "-u",
            self.service_name,
            "-n",
            str(lines),
            "--no-pager",
            timeout=15.0,
        )

        if exit_code == 0:
            return stdout
        else:
            if "permission denied" in stderr.lower():
                return "Permission denied - check sudoers configuration"
            return stderr or "Failed to retrieve logs"

    async def install_bt_bridge(self) -> InstallResult:
        """Install bt-bridge from GitHub.

        Clones the repo and runs the install script.
        Requires sudoers permission for the install script.
        """
        logger.info("Installing bt-bridge...")

        # Determine install location
        home = os.path.expanduser("~")
        install_dir = os.path.join(home, "pi-bt-bridge")

        # Check if already installed
        if os.path.exists(install_dir):
            logger.info("bt-bridge directory already exists at %s", install_dir)
            # Try to pull latest and reinstall
            exit_code, stdout, stderr = await self._run_command(
                "git",
                "-C",
                install_dir,
                "pull",
                timeout=60.0,
            )
            if exit_code != 0:
                return InstallResult(
                    success=False,
                    message="Failed to update existing bt-bridge installation",
                    output=stderr or stdout,
                    exit_code=exit_code,
                )
        else:
            # Clone the repository
            logger.info("Cloning bt-bridge to %s", install_dir)
            exit_code, stdout, stderr = await self._run_command(
                "git",
                "clone",
                "https://github.com/hemna/pi-bt-bridge.git",
                install_dir,
                timeout=120.0,
            )
            if exit_code != 0:
                return InstallResult(
                    success=False,
                    message="Failed to clone bt-bridge repository",
                    output=stderr or stdout,
                    exit_code=exit_code,
                )

        # Run the install script from the repo directory
        install_script = os.path.join(install_dir, "scripts", "install.sh")
        if not os.path.exists(install_script):
            return InstallResult(
                success=False,
                message="Install script not found at scripts/install.sh",
                output="",
                exit_code=-1,
            )

        # Make sure script is executable
        os.chmod(install_script, 0o755)

        logger.info("Running bt-bridge install script from %s...", install_dir)
        # Run from the repo directory so relative paths work
        # We use a wrapper script approach: create a temp script that cd's and runs
        # This avoids the sudoers complexity of bash -c
        # Also set PIP_BREAK_SYSTEM_PACKAGES to work around PEP 668 on Debian/Ubuntu
        wrapper_script = "/tmp/bt-bridge-install-wrapper.sh"
        wrapper_content = f"""#!/bin/bash
export PIP_BREAK_SYSTEM_PACKAGES=1
cd {install_dir}
exec bash scripts/install.sh
"""
        try:
            with open(wrapper_script, "w") as f:
                f.write(wrapper_content)
            os.chmod(wrapper_script, 0o755)

            exit_code, stdout, stderr = await self._run_command(
                "sudo",
                wrapper_script,
                timeout=300.0,  # 5 minutes for install
            )
        finally:
            # Clean up wrapper script
            try:
                os.unlink(wrapper_script)
            except OSError:
                pass

        combined_output = stdout
        if stderr:
            combined_output += "\n" + stderr

        if exit_code == 0:
            return InstallResult(
                success=True,
                message="bt-bridge installed successfully",
                output=combined_output,
                exit_code=exit_code,
            )
        else:
            message = "Installation failed"
            if "permission denied" in combined_output.lower():
                message = "Permission denied - check sudoers configuration"
            return InstallResult(
                success=False,
                message=message,
                output=combined_output,
                exit_code=exit_code,
            )
