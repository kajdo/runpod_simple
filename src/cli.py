"""Command-line interface for RunPod automation."""

import argparse
import sys
from typing import Optional
from rich.console import Console

from .config import Config
from .api_client import RunPodAPIClient
from .selector import (
    select_template,
    select_network_volume,
    select_pod_or_new,
    display_success,
    display_error,
    display_info
)
from .gpu_filter import select_optimal_gpu
from .pod_manager import PodManager
from .ssh_tunnel import SSHTunnel


console = Console()


class CLI:
    """Main CLI application."""
    
    def __init__(self):
        self.config: Optional[Config] = None
        self.api: Optional[RunPodAPIClient] = None
        self.pod_manager: Optional[PodManager] = None
        self.current_pod_id: Optional[str] = None
    
    def init_config(self) -> bool:
        """Initialize configuration."""
        try:
            self.config = Config()
            is_valid, error_msg = self.config.validate()
            
            if not is_valid:
                display_error(f"Configuration error: {error_msg}")
                return False
            
            display_success(f"API key loaded")
            
            if self.config.ssh_key_path:
                display_success(f"SSH key found: {self.config.ssh_key_path}")
            elif self.config.ssh_password:
                display_success("SSH password configured")
            else:
                display_error("No SSH authentication method configured")
                return False
            
            return True
        
        except ValueError as e:
            display_error(str(e))
            return False
    
    def init_api(self) -> bool:
        """Initialize API client."""
        try:
            self.api = RunPodAPIClient(self.config.api_key)
            self.pod_manager = PodManager(self.api)
            display_success("API client initialized")
            return True
        except Exception as e:
            display_error(f"Failed to initialize API client: {e}")
            return False
    
    def deploy_workflow(self, args) -> int:
        """Main deployment workflow."""
        
        if not self.init_config():
            return 1
        
        if not self.init_api():
            return 1
        
        assert self.config is not None
        assert self.api is not None
        assert self.pod_manager is not None
        
        api = self.api
        pod_manager = self.pod_manager
        
        try:
            pods = api.get_pods()
            
            existing_pod_id = None
            if not args.no_reuse:
                existing_pod_id = select_pod_or_new(pods)
            
            if existing_pod_id:
                self._reuse_existing_pod(existing_pod_id, args)
            else:
                self._deploy_new_pod(args)
            
            return 0
        
        except KeyboardInterrupt:
            display_info("\nDeployment cancelled by user")
            return 130
        except Exception as e:
            display_error(f"Deployment failed: {e}")
            # Only print traceback if in debug mode or if explicitly requested
            # import traceback
            # traceback.print_exc()
            return 1
    
    def _reuse_existing_pod(self, pod_id: str, args) -> None:
        """Reuse existing pod and create tunnels."""
        
        display_info(f"Reusing existing pod: {pod_id}")
        
        try:
            conn = self.pod_manager.get_existing_pod(pod_id)
            self.current_pod_id = pod_id
            
            self._create_tunnels(conn, args.no_cleanup)
        
        except Exception as e:
            display_error(f"Failed to reuse pod: {e}")
            raise
    
    def _deploy_new_pod(self, args) -> None:
        """Deploy new pod and create tunnels."""
        
        templates = self.api.get_templates(
            include_public=False,
            include_runpod=False,
            include_endpoint_bound=False
        )
        
        if not templates:
            display_error("No templates found")
            return
        
        template_id = None
        volume_id = None
        volume = None
        use_defaults = args.defaults
        
        if args.template_id:
            template_id = args.template_id
            display_info(f"Using specified template ID: {template_id}")
            use_defaults = False
        elif use_defaults:
            default_template_name = self.config.get_default_template()
            if not default_template_name:
                display_error("DEFAULT_TEMPLATE not set in .env")
                return
            
            # Find template by name
            template = next((t for t in templates if t.name == default_template_name), None)
            if not template:
                display_error(f"Template '{default_template_name}' not found. Available templates:")
                for t in templates:
                    display_error(f"  - {t.name}")
                return
            
            template_id = template.id
            display_info(f"Using default template: {template.name}")
        else:
            template_id = select_template(templates, auto_select=(len(templates) == 1))
        
        volumes = self.api.get_network_volumes()
        
        if args.volume_id:
            volume_id = args.volume_id
            display_info(f"Using specified volume ID: {volume_id}")
            use_defaults = False
        elif use_defaults:
            default_volume_name = self.config.get_default_network_volume()
            if default_volume_name is not None:
                # Find volume by name
                volume = next((v for v in volumes if v.name == default_volume_name), None)
                if not volume:
                    display_error(f"Network volume '{default_volume_name}' not found. Available volumes:")
                    for v in volumes:
                        display_error(f"  - {v.name}")
                    return
                volume_id = volume.id
                display_info(f"Using default network volume: {volume.name}")
            else:
                # DEFAULT_NETWORK_VOLUME is null or not set - no network volume
                display_info("Using default: no network volume")
                # Create a dummy volume with no datacenter for cross-region GPU selection
                from .api_client import NetworkVolume
                volume = NetworkVolume(id="", name="None", size=0, data_center_id=None)
        else:
            if not volumes:
                display_error("No network volumes found")
                return
            volume_id = select_network_volume(volumes, auto_select=(len(volumes) == 1))
        
        if not volume:
            volume = next((v for v in volumes if v.id == volume_id), None)
            if not volume:
                display_error(f"Volume {volume_id} not found")
                return
        
        # Resolve template ports
        selected_template = next((t for t in templates if t.id == template_id), None)
        template_ports = selected_template.ports if selected_template else None
        
        # Get GPU types and availability for the specific datacenter or all regions
        if volume.data_center_id:
            gpu_types, availability = self.api.get_gpu_types(volume.data_center_id)
        else:
            # Query across all datacenters
            gpu_types, availability = self.api.get_gpu_types(None)
        
        # Get GPU filters from defaults if using defaults mode
        min_cost = None
        max_cost = None
        allow_two_gpus = None
        
        if use_defaults:
            min_cost = self.config.get_default_min_cost_per_hour()
            max_cost = self.config.get_default_max_cost_per_hour()
            allow_two_gpus = self.config.get_default_allow_two_gpus()
        
        gpu_config = select_optimal_gpu(
            volume, 
            gpu_types, 
            availability=availability,
            auto_select=args.auto_select_gpu,
            min_cost=min_cost,
            max_cost=max_cost,
            allow_two_gpus=allow_two_gpus,
            quiet=use_defaults
        )
        
        pod = self.pod_manager.deploy_pod(
            template_id=template_id,
            network_volume_id=volume_id,
            gpu_config=gpu_config,
            ports=template_ports
        )
        
        self.current_pod_id = pod.id
        
        running_pod = self.pod_manager.wait_for_running(pod.id)
        
        conn = self.pod_manager.get_connection_details(pod.id)
        
        self._create_tunnels(conn, args.no_cleanup)
    
    def _create_tunnels(self, conn: dict, no_cleanup: bool) -> None:
        """Create SSH tunnels and keep them alive."""
        
        display_info(f"\n[bold]Connection Details:[/bold]")
        display_info(f"  Pod IP:     {conn['ip']}")
        display_info(f"  SSH Port:    {conn['ssh_port']}")
        display_info(f"  Pod Name:    {conn['pod_name']}")
        display_info(f"  GPU:         {conn['gpu_name']}")
        
        tunnel = SSHTunnel(
            pod_ip=conn["ip"],
            ssh_port=conn["ssh_port"],
            username="root",
            ssh_key_path=self.config.ssh_key_path,
            password=self.config.ssh_password
        )
        
        success, message, local_ip = tunnel.start_tunnels()
        
        if not success:
            display_error(message)
            if not no_cleanup and self.current_pod_id:
                self.pod_manager.terminate_pod(self.current_pod_id)
            sys.exit(1)
        
        display_info(f"\n{message}")
        
        # We handle cleanup via the try/except KeyboardInterrupt below.
        # This avoids double-cleanup race conditions that occurred with signal handlers.
        
        try:
            tunnel.wait()
        except KeyboardInterrupt:
            tunnel.stop_all()
            if not no_cleanup and self.current_pod_id:
                # self.pod_manager is Optional, but init_api guarantees it's set
                if self.pod_manager:
                     self.pod_manager.terminate_pod(self.current_pod_id)
            display_success("Cleanup complete")
    
    def list_pods(self, args) -> int:
        """List all pods."""
        
        if not self.init_config():
            return 1
        
        if not self.init_api():
            return 1
        
        try:
            pods = self.api.get_pods()
            
            if not pods:
                display_info("No pods found")
                return 0
            
            from rich.table import Table
            
            table = Table(title="All Pods")
            table.add_column("Name", style="green")
            table.add_column("Status", style="blue")
            table.add_column("GPU", style="magenta")
            table.add_column("IP", style="yellow")
            table.add_column("ID", style="dim")
            
            for pod in pods:
                gpu_name = "N/A"
                if pod.gpu and "displayName" in pod.gpu:
                    gpu_name = pod.gpu["displayName"]
                
                status_style = "green" if pod.status == "RUNNING" else "yellow"
                
                table.add_row(
                    pod.name,
                    f"[{status_style}]{pod.status}[/{status_style}]",
                    gpu_name,
                    pod.public_ip or "N/A",
                    pod.id
                )
            
            console.print(table)
            return 0
        
        except Exception as e:
            display_error(f"Failed to list pods: {e}")
            return 1
    
    def delete_pod(self, args) -> int:
        """Delete a specific pod."""
        
        if not self.init_config():
            return 1
        
        if not self.init_api():
            return 1
        
        try:
            result = self.pod_manager.terminate_pod(args.pod_id)
            return 0 if result else 1
        except Exception as e:
            display_error(f"Failed to delete pod: {e}")
            return 1


def main() -> int:
    """Main entry point."""
    
    parser = argparse.ArgumentParser(
        description="RunPod automation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    deploy_parser = subparsers.add_parser("deploy", help="Deploy a new pod or reuse existing")
    deploy_parser.add_argument(
        "--no-reuse",
        action="store_true",
        help="Skip existing pod selection, always create new"
    )
    deploy_parser.add_argument(
        "--template-id",
        help="Template ID to use (skip selection)"
    )
    deploy_parser.add_argument(
        "--volume-id",
        help="Network volume ID to use (skip selection)"
    )
    deploy_parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't delete pod on exit"
    )
    deploy_parser.add_argument(
        "--auto-select-gpu",
        action="store_true",
        help="Auto-select cheapest GPU without prompting"
    )
    deploy_parser.add_argument(
        "--defaults",
        action="store_true",
        help="Use default configuration from .env (no interactive prompts)"
    )
    
    subparsers.add_parser("list", help="List all pods")
    
    delete_parser = subparsers.add_parser("delete", help="Delete a specific pod")
    delete_parser.add_argument("pod_id", help="Pod ID to delete")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = CLI()
    
    if args.command == "deploy":
        return cli.deploy_workflow(args)
    elif args.command == "list":
        return cli.list_pods(args)
    elif args.command == "delete":
        return cli.delete_pod(args)
    else:
        parser.print_help()
        return 1
