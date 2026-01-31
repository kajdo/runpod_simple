"""Pod lifecycle management."""

import time
from typing import Optional, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

from .api_client import RunPodAPIClient, Pod
from .selector import display_success, display_error, display_info


console = Console()


class PodManager:
    """Manages pod deployment and lifecycle."""
    
    def __init__(self, api_client: RunPodAPIClient):
        self.api = api_client
        self.current_pod_id: Optional[str] = None
    
    def deploy_pod(
        self,
        template_id: Optional[str],
        network_volume_id: Optional[str],
        gpu_config: dict,
        name: Optional[str] = None,
        ports: Optional[List[str]] = None
    ) -> Pod:
        """Deploy a new pod."""
        
        if not name:
            import datetime
            name = f"pod-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        display_info(f"Deploying pod: {name}")
        display_info(f"  Template ID: {template_id}")
        if network_volume_id:
            display_info(f"  Network Volume: {network_volume_id}")
        else:
            display_info(f"  Network Volume: None (using container disk)")
        display_info(f"  GPU: {gpu_config['display_name']} x{gpu_config['gpu_count']}")
        
        try:
            pod = self.api.create_pod(
                name=name,
                template_id=template_id,
                network_volume_id=network_volume_id,
                gpu_type_ids=[gpu_config["gpu_type_id"]],
                gpu_count=gpu_config["gpu_count"],
                ports=ports
            )
            
            self.current_pod_id = pod.id
            display_success(f"Pod created: {pod.id}")
            return pod
        
        except RuntimeError as e:
            error_msg = str(e)
            
            if "Bad Request" in error_msg or "400" in error_msg:
                display_error(f"\nGPU deployment failed: {error_msg}")
                display_error("\nPossible reasons:")
                display_error("  • GPU is unavailable in the selected datacenter")
                display_error("  • Network volume is in a different datacenter")
                display_error("  • Insufficient quota or balance")
                display_error("\nTry:")
                display_error("  • Selecting a different GPU")
                display_error("  • Using a network volume in a different datacenter")
                display_error("  • Checking your RunPod account balance and quotas")
            
            raise
    
    def wait_for_running(
        self,
        pod_id: str,
        timeout: Optional[int] = None
    ) -> Pod:
        """Wait for pod to reach RUNNING status with public IP and SSH port."""
        
        display_info("Waiting for pod to be ready...")
        
        start_time = time.time()
        check_interval = 5
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task(
                "Initializing pod...",
                total=None
            )
            
            while True:
                if timeout and (time.time() - start_time) > timeout:
                    raise TimeoutError(f"Pod did not become ready within {timeout} seconds")
                
                pod = self.api.get_pod(pod_id)
                elapsed = int(time.time() - start_time)
                
                if pod.status == "RUNNING":
                    # Check for IP and SSH port
                    has_ip = bool(pod.public_ip)
                    has_ssh = bool(pod.port_mappings and "22" in pod.port_mappings)
                    
                    if has_ip and has_ssh:
                        progress.update(task, completed=100, total=100)
                        display_success(f"Pod is RUNNING: {pod.name}")
                        return pod
                    
                    # Update status message detailing what is missing
                    missing = []
                    if not has_ip: missing.append("Public IP")
                    if not has_ssh: missing.append("SSH Port")
                    
                    progress.update(
                        task,
                        description=f"Pod RUNNING, waiting for: {', '.join(missing)}... ({elapsed}s)"
                    )
                
                elif pod.status in ["TERMINATED", "EXITED"]:
                    raise RuntimeError(f"Pod failed with status: {pod.status}")
                else:
                    progress.update(
                        task,
                        description=f"Pod status: {pod.status} ({elapsed}s)"
                    )
                
                time.sleep(check_interval)
    
    def get_connection_details(self, pod_id: str) -> dict:
        """Extract connection details from pod."""
        
        pod = self.api.get_pod(pod_id)
        
        if not pod.public_ip:
            raise RuntimeError(f"Pod {pod_id} does not have a public IP yet")
        
        # Try to get SSH port from GraphQL first (reliable TCP port)
        ssh_port = self.api.get_pod_ssh_port_from_graphql(pod_id)
        
        # Fallback to REST API if GraphQL fails (though REST might give UDP port)
        if not ssh_port:
            ssh_port = pod.port_mappings.get("22")
            
        if not ssh_port:
            raise RuntimeError("SSH port (22) not mapped")
        
        return {
            "pod_id": pod.id,
            "pod_name": pod.name,
            "ip": pod.public_ip,
            "ssh_port": ssh_port,
            "gpu_name": pod.gpu.get("displayName", "Unknown") if pod.gpu else "Unknown"
        }
    
    def get_existing_pod(self, pod_id: str) -> dict:
        """Get connection details for existing pod."""
        
        pod = self.api.get_pod(pod_id)
        
        if pod.status != "RUNNING":
            raise RuntimeError(f"Pod {pod_id} is not running (status: {pod.status})")
        
        return self.get_connection_details(pod_id)
    
    def terminate_pod(self, pod_id: str) -> bool:
        """Terminate a pod."""
        
        display_info(f"Terminating pod {pod_id}...")
        
        try:
            self.api.delete_pod(pod_id)
            display_success(f"Pod {pod_id} terminated")
            return True
        except Exception as e:
            # If pod is already gone (404), consider it a success
            if "404" in str(e):
                display_success(f"Pod {pod_id} already terminated")
                return True
                
            display_error(f"Failed to terminate pod: {e}")
            return False
