"""SSH tunnel management with network accessibility."""

import subprocess
import socket
import signal
import sys
import time
import os
import stat
from typing import List, Tuple, Optional, Any
from rich.console import Console
from rich.table import Table
from rich import box

from .selector import display_success, display_warning, display_error, display_info


console = Console()


class SSHTunnel:
    """Manages SSH tunnels for RunPod pods."""
    
    def __init__(
        self,
        pod_ip: str,
        ssh_port: int,
        username: str = "root",
        ssh_key_path: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.pod_ip = pod_ip
        self.ssh_port = ssh_port
        self.username = username
        self.ssh_key_path = ssh_key_path
        self.password = password
        self.processes: List[Any] = []
        self.tunnels = [
            {"local": 11434, "remote": 11434, "name": "Ollama API"},
            {"local": 8080, "remote": 8080, "name": "WebUI"},
            {"local": 2222, "remote": 22, "name": "SSH (Local)"}
        ]
        
        if not ssh_key_path and not password:
            raise ValueError("Either SSH key or password is required")
    
    @staticmethod
    def detect_local_ip() -> str:
        """Detect local IP address, preferring 192.168.* range."""
        try:
            import netifaces
            
            interfaces = netifaces.interfaces()
            candidates = []
            
            for iface in interfaces:
                if any(skip in iface for skip in ["docker", "virbr", "veth", "lo", "br-"]):
                    continue
                
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get("addr", "")
                        if ip and not ip.startswith("127."):
                            candidates.append((ip, iface))
            
            candidates.sort(key=lambda x: (
                0 if x[0].startswith("192.168.") else
                1 if x[0].startswith("10.") else
                2 if x[0].startswith("172.") else 3
            ))
            
            if candidates:
                console.print(f"[dim]Detected local IPs:[/dim]")
                for ip, iface in candidates[:3]:
                    console.print(f"  [dim]•[/dim] {ip} ({iface})")
                return candidates[0][0]
        
        except ImportError:
            pass
        
        fallback_ip = "localhost"
        console.print(f"[dim]Using fallback IP: {fallback_ip}[/dim]")
        return fallback_ip
    
    def _build_ssh_command(
        self,
        tunnels: List[dict],
        bind_addr: str
    ) -> List[str]:
        """Build SSH command with multiple tunnels."""
        
        ssh_cmd = [
            "ssh",
            "-4",
        ]
        
        for tunnel in tunnels:
            ssh_cmd.extend([
                "-L", f"{bind_addr}:{tunnel['local']}:127.0.0.1:{tunnel['remote']}"
            ])
            
        ssh_cmd.extend([
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "TCPKeepAlive=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectionAttempts=60",
            "-N",
            "-T",
            f"{self.username}@{self.pod_ip}",
            "-p", str(self.ssh_port)
        ])
        
        if self.ssh_key_path:
            ssh_cmd.extend(["-i", self.ssh_key_path])
        
        return ssh_cmd
    
    def _create_tunnel_with_password(
        self,
        ssh_cmd: List[str]
    ):
        """Create SSH tunnel using password authentication with pexpect."""
        import pexpect
        
        ssh_str = " ".join(ssh_cmd)
        console.print(f"[dim]Starting tunnel with password auth...[/dim]")
        
        try:
            child = pexpect.spawn(ssh_str, timeout=30)
            index = child.expect([r"password:", pexpect.EOF, pexpect.TIMEOUT])
            
            if index == 0 and self.password:
                child.sendline(self.password)
                child.expect(pexpect.EOF, timeout=5)
            
            return child
        except Exception as e:
            raise RuntimeError(f"Failed to create password-authenticated tunnel: {e}")
    
    def _create_tunnel_with_key(
        self,
        ssh_cmd: List[str]
    ) -> subprocess.Popen:
        """Create SSH tunnel using key authentication."""
        console.print(f"[dim]Starting tunnel with SSH key...[/dim]")
        
        try:
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
            
            time.sleep(1)
            
            if process.poll() is not None:
                _, stderr = process.communicate()
                raise RuntimeError(f"SSH process exited immediately: {stderr.decode('utf-8', errors='ignore')}")
            
            return process
        except Exception as e:
            raise RuntimeError(f"Failed to create SSH tunnel: {e}")

    def _create_ssh_helper_script(self) -> str:
        """Create a helper script for SSH access if it doesn't exist."""
        script_path = os.path.expanduser("~/.local/bin/runpod_ssh")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        
        if os.path.exists(script_path):
            return "runpod_ssh"
            
        content = (
            "#!/usr/bin/env bash\n"
            "# Auto-generated by runpod-simple\n"
            "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@localhost -p 2222 \"$@\"\n"
        )
        
        try:
            with open(script_path, "w") as f:
                f.write(content)
            
            # Make executable
            st = os.stat(script_path)
            os.chmod(script_path, st.st_mode | stat.S_IEXEC)
            
            display_success(f"Created helper script: {script_path}")
            return "runpod_ssh"
        except Exception as e:
            display_warning(f"Failed to create helper script: {e}")
            return "ssh ... (script failed)"

    def start_tunnels(self) -> Tuple[bool, str, str]:
        """
        Start SSH tunnels with network binding.
        
        Returns:
            Tuple of (success, message, local_ip)
        """
        
        local_ip = self.detect_local_ip()
        
        # Check if ports are already in use
        for tunnel in self.tunnels:
            if self._is_port_in_use(tunnel['local']):
                 display_warning(f"Port {tunnel['local']} is already in use locally. Tunneling might fail.")
        
        for bind_addr in ["0.0.0.0", "127.0.0.1"]:
            if bind_addr == "0.0.0.0":
                display_info(f"Trying network-wide binding ({bind_addr})...")
            else:
                display_warning(
                    f"Network-wide binding failed. Using localhost-only binding.\n"
                    f"  To access from other machines, run with sudo."
                )
            
            # We don't check _try_bind_address here for every port because we want SSH to handle the binding.
            # If SSH fails to bind, it will exit (ExitOnForwardFailure=yes).
            
            try:
                ssh_cmd = self._build_ssh_command(self.tunnels, bind_addr)
                
                # Log the command for debugging (masking key path slightly if needed, but here it's fine)
                cmd_str = " ".join(ssh_cmd)
                # console.print(f"[dim]Command: {cmd_str}[/dim]") 
                
                if self.ssh_key_path:
                    process = self._create_tunnel_with_key(ssh_cmd)
                else:
                    process = self._create_tunnel_with_password(ssh_cmd)
                
                self.processes.append(process)
                
                # Verify process is still alive after a short wait
                time.sleep(2)
                
                is_alive = True
                error_msg = "Unknown error"
                
                if hasattr(process, 'poll'):  # subprocess.Popen
                    if process.poll() is not None:
                        is_alive = False
                        _, stderr = process.communicate()
                        error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unknown error"
                elif hasattr(process, 'isalive'):  # pexpect.spawn
                    if not process.isalive():
                        is_alive = False
                        error_msg = str(process.before) if process.before else "Process exited"
                
                if not is_alive:
                    raise RuntimeError(f"SSH process exited immediately: {error_msg}")

                # If we got here, success!
                
                # Ensure helper script exists
                helper_cmd = self._create_ssh_helper_script()
                
                console.print()
                table = Table(title=f"SSH Tunnels to {self.pod_ip}", box=box.ROUNDED)
                table.add_column("Service", style="cyan", no_wrap=True)
                table.add_column("Local Address", style="green")
                table.add_column("Remote Endpoint (Pod)", style="yellow")
                table.add_column("Access URL", style="bold blue")

                # Add SSH Tunnel entry
                table.add_row(
                    "SSH Tunnel",
                    "-",
                    f"{self.pod_ip}:{self.ssh_port}",
                    "-"
                )

                for tunnel in self.tunnels:
                    local_bind = f"{bind_addr}:{tunnel['local']}"
                    
                    # Show Pod IP + Remote Port as requested
                    remote_target = f"{self.pod_ip}:{tunnel['remote']}"
                    
                    # Use appropriate IP for URL based on binding
                    display_ip = "127.0.0.1" if bind_addr == "127.0.0.1" else local_ip
                    url = f"http://{display_ip}:{tunnel['local']}"
                    
                    # Special handling for SSH Local tunnel
                    if tunnel['remote'] == 22:
                        url = helper_cmd
                    
                    table.add_row(
                        tunnel['name'],
                        local_bind,
                        remote_target,
                        url
                    )
                
                console.print(table)
                
                if bind_addr == "127.0.0.1":
                    success_msg = "Tunnels created (localhost-only). Run with sudo for network access."
                else:
                    success_msg = "Tunnels created with network-wide access."
                
                return True, success_msg, local_ip
                
            except Exception as e:
                self.stop_all()
                display_error(f"Binding {bind_addr} failed: {e}")
                continue # Try next bind_addr
        
        return False, "Failed to create tunnels. Check permissions and port availability.", local_ip

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a local port is in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    
    def wait(self) -> None:
        """Wait for all tunnel processes (fail-fast)."""
        if not self.processes:
            return
        
        display_info("Tunnels active. Press Ctrl+C to stop.")
        
        try:
            for process in self.processes:
                if hasattr(process, 'wait'):
                    # subprocess.Popen
                    process.wait()
                elif hasattr(process, 'expect'):
                    # pexpect.spawn
                    import pexpect
                    try:
                        process.expect(pexpect.EOF, timeout=None)
                    except (pexpect.EOF, pexpect.TIMEOUT):
                        pass
        except KeyboardInterrupt:
            display_info("\nReceived interrupt signal...")
            raise
    
    def stop_all(self) -> None:
        """Stop all tunnel processes."""
        if not self.processes:
            return
        
        display_info("Stopping tunnels...")
        
        for process in self.processes:
            try:
                if hasattr(process, 'terminate'):
                    # subprocess.Popen
                    process.terminate()
                    try:
                        if hasattr(process, 'wait'):
                            process.wait(timeout=5)
                    except:
                        process.kill()
                elif hasattr(process, 'close'):
                    # pexpect.spawn
                    process.close()
            except:
                try:
                    if hasattr(process, 'kill'):
                        process.kill()
                except:
                    pass
        
        self.processes.clear()
        display_success("All tunnels stopped")
