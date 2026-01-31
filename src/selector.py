"""Interactive selection prompts using rich."""

from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .api_client import Template, NetworkVolume, Pod


console = Console()


def select_template(templates: List[Template], auto_select: bool = False) -> str:
    """Prompt user to select a template."""
    
    if not templates:
        raise ValueError("No templates found")
    
    if auto_select or len(templates) == 1:
        selected = templates[0]
        display_success(f"Auto-selected template: {selected.name}")
        return selected.id
    
    table = Table(title="Available Templates")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Name", style="green")
    table.add_column("Image", style="blue")
    table.add_column("ID", style="yellow")
    
    for idx, tmpl in enumerate(templates, 1):
        table.add_row(
            str(idx),
            tmpl.name[:40],
            tmpl.image_name[:50],
            tmpl.id
        )
    
    console.print(table)
    
    while True:
        choice = Prompt.ask(
            "Select template",
            choices=[str(i) for i in range(1, len(templates) + 1)],
            default="1"
        )
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(templates):
                return templates[idx].id


def select_network_volume(volumes: List[NetworkVolume], auto_select: bool = False) -> str:
    """Prompt user to select a network volume."""
    
    if not volumes:
        raise ValueError("No network volumes found")
    
    if auto_select or len(volumes) == 1:
        selected = volumes[0]
        display_success(f"Auto-selected network volume: {selected.name} ({selected.size}GB)")
        return selected.id
    
    table = Table(title="Available Network Volumes")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Name", style="green")
    table.add_column("Size (GB)", style="blue")
    table.add_column("Datacenter", style="magenta")
    table.add_column("ID", style="yellow")
    
    for idx, vol in enumerate(volumes, 1):
        table.add_row(
            str(idx),
            vol.name,
            str(vol.size),
            vol.data_center_id,
            vol.id
        )
    
    console.print(table)
    
    while True:
        choice = Prompt.ask(
            "Select network volume",
            choices=[str(i) for i in range(1, len(volumes) + 1)],
            default="1"
        )
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(volumes):
                return volumes[idx].id


def select_pod_or_new(pods: List[Pod]) -> Optional[str]:
    """Prompt user to reuse existing pod or create new one."""
    
    running_pods = [p for p in pods if p.status == "RUNNING"]
    
    if not running_pods:
        console.print("[yellow]No running pods found. Creating new pod.[/yellow]")
        return None
    
    table = Table(title="Existing Running Pods")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Name", style="green")
    table.add_column("Status", style="blue")
    table.add_column("GPU", style="magenta")
    table.add_column("IP", style="yellow")
    table.add_column("ID", style="dim")
    
    for idx, pod in enumerate(running_pods, 1):
        gpu_info = pod.gpu
        gpu_name = "N/A"
        if gpu_info and "displayName" in gpu_info:
            gpu_name = f"{gpu_info['displayName']}"
        
        table.add_row(
            str(idx),
            pod.name,
            pod.status,
            gpu_name,
            pod.public_ip or "N/A",
            pod.id
        )
    
    console.print(table)
    
    console.print("\n[cyan]Options:[/cyan]")
    console.print("  [1-N] Select existing pod to reuse")
    console.print("  [0]   Create new pod")
    
    while True:
        choice = Prompt.ask(
            "Select option",
            choices=[str(i) for i in range(0, len(running_pods) + 1)],
            default="0"
        )
        
        if choice.isdigit():
            idx = int(choice)
            if idx == 0:
                return None
            elif 1 <= idx <= len(running_pods):
                return running_pods[idx - 1].id


def confirm_action(message: str) -> bool:
    """Prompt user for yes/no confirmation."""
    return Confirm.ask(message, default=True)


def display_success(message: str) -> None:
    """Display success message."""
    console.print(f"[green]✓[/green] {message}")


def display_warning(message: str) -> None:
    """Display warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def display_error(message: str) -> None:
    """Display error message."""
    console.print(f"[red]✗[/red] {message}")


def display_info(message: str) -> None:
    """Display info message."""
    console.print(f"[cyan]ℹ[/cyan] {message}")
