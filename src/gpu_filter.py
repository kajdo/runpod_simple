"""GPU filtering and selection logic."""

from typing import Dict, Optional, List, Any
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .api_client import GPUInfo, NetworkVolume
from .selector import display_success, display_warning, display_error, display_info


console = Console()


def select_optimal_gpu(
    volume: NetworkVolume,
    gpu_types: List[GPUInfo],
    availability: Dict[str, int] = {},
    min_vram_gb: int = 24,
    auto_select: bool = False,
    min_cost: Optional[float] = None,
    max_cost: Optional[float] = None,
    allow_two_gpus: Optional[bool] = None,
    quiet: bool = False,
    cloud_type: str = "SECURE",
    is_spot: bool = False
) -> Dict[str, Any]:
    """
    Find optimal GPU configuration for given network volume.
    
    Args:
        volume: Network volume with datacenter information
        gpu_types: List of available GPU types
        availability: Dict mapping gpu_id to max available count
        min_vram_gb: Minimum VRAM required
        auto_select: If True, auto-select cheapest available without prompting
        min_cost: Minimum hourly cost filter
        max_cost: Maximum hourly cost filter
        allow_two_gpus: If False, only allow Qty=1 (no dual GPU)
        quiet: If True, don't display the GPU selection table
        cloud_type: "SECURE" or "COMMUNITY"
        is_spot: If True, use spot pricing (only for Community Cloud)
    
    Returns dict with:
        - gpu_type_id: str
        - gpu_count: int
        - cost_per_hour: float
        - total_vram_gb: int
        - display_name: str
    """
    
    datacenter = volume.data_center_id if volume and volume.data_center_id else "All regions"
    is_community = (cloud_type == "COMMUNITY")
    
    display_success(f"Finding GPU for datacenter: {datacenter}")
    display_success(f"Minimum VRAM requirement: {min_vram_gb} GB")
    if is_community:
        if is_spot:
            display_success("Using Community Cloud (Spot) pricing")
        else:
            display_success("Using Community Cloud (On-Demand) pricing")
    
    candidates = []
    
    for gpu in gpu_types:
        memory = gpu.memory_in_gb
        avail_count = availability.get(gpu.id, 0)
        
        # Determine price
        price = gpu.secure_price
        if is_community:
             if is_spot:
                 # Use spot price if available, fallback to secure/base (though technically improper, prevents crash)
                 price = gpu.community_spot_price if gpu.community_spot_price else gpu.secure_price
             else:
                 # Use community on-demand price
                 price = gpu.community_price if gpu.community_price else gpu.secure_price
        
        if not price:
            continue

        # Option 1: Single GPU (if memory sufficient and at least 1 available)
        if memory >= min_vram_gb and avail_count >= 1:
            candidates.append({
                "gpu_type_id": gpu.id,
                "gpu_count": 1,
                "cost_per_hour": price,
                "total_vram_gb": memory,
                "display_name": gpu.display_name,
                "cost_per_gb_vram": price / memory,
                "is_available": True,
                "stock_status": gpu.stock_status
            })
            
        # Option 2: Dual GPU (if single not sufficient, but pair is, and at least 2 available)
        # Note: We only suggest this if a single GPU wouldn't be enough (per user request "add available gpus with less than the threshold")
        # Or should we always suggest it? User said "add available gpus with less than the threshold".
        # So strict check: memory < min_vram_gb
        if memory < min_vram_gb and (memory * 2) >= min_vram_gb and avail_count >= 2:
             candidates.append({
                "gpu_type_id": gpu.id,
                "gpu_count": 2,
                "cost_per_hour": price * 2,
                "total_vram_gb": memory * 2,
                "display_name": gpu.display_name,
                "cost_per_gb_vram": price / memory, # Price per GB constant
                "is_available": True,
                "stock_status": gpu.stock_status
            })
    
    # Apply cost filters
    if min_cost is not None or max_cost is not None:
        candidates = [
            cand for cand in candidates
            if (min_cost is None or cand["cost_per_hour"] >= min_cost) and
               (max_cost is None or cand["cost_per_hour"] <= max_cost)
        ]
    
    # Apply allow_two_gpus filter
    if allow_two_gpus is False:
        candidates = [cand for cand in candidates if cand["gpu_count"] == 1]
    
    if not candidates:
        raise RuntimeError(
            f"No available GPU configuration found matching criteria in {datacenter}.\n"
            f"Try checking another datacenter or lowering requirements."
        )
    
    # Sort by cost (asc) then availability (high to low)
    def stock_score(status):
        if status == "High": return 3
        if status == "Medium": return 2
        if status == "Low": return 1
        return 0
    
    # Sort key: (Cost, -AvailabilityScore)
    # Python sorts are stable, so we can sort by availability first, then by cost?
    # No, tuple sort: (cost, -score)
    candidates.sort(key=lambda x: (x["cost_per_hour"], -stock_score(x["stock_status"])))
    
    cheapest = candidates[0]
    
    count_str = f"x{cheapest['gpu_count']}" if cheapest['gpu_count'] > 1 else ""
    display_success(f"Selected: {cheapest['display_name']} {count_str} ({cheapest['total_vram_gb']}GB) @ ${cheapest['cost_per_hour']:.2f}/hr")
    
    if auto_select or quiet:
        return cheapest
    
    table_title = f"Available GPUs (>= {min_vram_gb}GB) in {datacenter}"
    if is_community:
        table_title += " [Community Spot]" if is_spot else " [Community On-Demand]"
        
    table = Table(title=table_title)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Name", style="green")
    table.add_column("Qty", style="bold yellow")
    table.add_column("Total VRAM", style="blue")
    table.add_column("Cost/hr", style="magenta")
    table.add_column("Stock", style="white")
    table.add_column("ID", style="dim")
    
    for idx, cand in enumerate(candidates, 1):
        is_cheapest = cand == cheapest
        
        cost_str = f"${cand['cost_per_hour']:.2f}"
        if is_cheapest:
            cost_str = f"[bold green]{cost_str}[/bold green]"
        
        stock_str = cand.get("stock_status") or "Unknown"
        stock_style = "white"
        if stock_str == "High": stock_style = "green"
        elif stock_str == "Medium": stock_style = "yellow"
        elif stock_str == "Low": stock_style = "red"
        
        table.add_row(
            str(idx),
            cand["display_name"] + (" [bold]★[/bold]" if is_cheapest else ""),
            str(cand["gpu_count"]),
            f"{cand['total_vram_gb']}GB",
            cost_str,
            f"[{stock_style}]{stock_str}[/{stock_style}]",
            cand["gpu_type_id"][:20] + "..." if len(cand["gpu_type_id"]) > 20 else cand["gpu_type_id"]
        )
    
    console.print(table)
    
    while True:
        default_choice = "1"
        prompt_msg = f"Select GPU [default: {default_choice}]: "
        choice = Prompt.ask(prompt_msg, default=default_choice)
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                selected = candidates[idx]
                count_suffix = f" x{selected['gpu_count']}" if selected['gpu_count'] > 1 else ""
                display_success(f"Selected: {selected['display_name']}{count_suffix} ({selected['total_vram_gb']}GB) @ ${selected['cost_per_hour']:.2f}/hr")
                return selected


def select_multi_gpu_combination(
    gpu_types: List[GPUInfo],
    target_vram_gb: int = 24
) -> Optional[Dict[str, Any]]:
    """
    Find optimal multi-GPU combination for target VRAM.
    
    This is a placeholder for future enhancement where we combine
    multiple smaller GPUs to meet the VRAM requirement.
    """
    
    display_warning("Multi-GPU selection not yet implemented.")
    return None

