"""RunPod REST API client."""

import time
import requests
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


API_BASE_URL = "https://rest.runpod.io/v1"


@dataclass
class Template:
    """RunPod template representation."""
    id: str
    name: str
    image_name: str
    container_disk_in_gb: int
    volume_in_gb: int
    ports: List[str]
    is_serverless: bool


@dataclass
class NetworkVolume:
    """RunPod network volume representation."""
    id: str
    name: str
    size: int
    data_center_id: Optional[str]


@dataclass
class Pod:
    """RunPod pod representation."""
    id: str
    name: str
    status: str
    image: str
    public_ip: Optional[str]
    port_mappings: Dict[str, int]
    gpu: Optional[Dict[str, Any]]
    network_volume_id: Optional[str]
    template_id: Optional[str]


@dataclass
class GPUInfo:
    """GPU information."""
    id: str
    display_name: str
    memory_in_gb: int
    secure_price: float
    community_spot_price: Optional[float] = None
    stock_status: Optional[str] = None


class RunPodAPIClient:
    """REST API client for RunPod."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Any:
        """Make API request with retry logic."""
        url = f"{API_BASE_URL}{endpoint}"
        last_error = None
        last_response_text = ""
        
        for attempt in range(retry_count):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    timeout=30
                )
                
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                
                if response.status_code >= 400:
                    last_response_text = response.text
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", error_data.get("message", last_response_text))
                    except:
                        error_msg = last_response_text
                    
                    last_error = f"{response.status_code}: {error_msg}"
                    
                    if response.status_code != 429:
                        break
                
                response.raise_for_status()
                return response.json()
            
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < retry_count - 1:
                    time.sleep(1)
        
        if last_response_text and isinstance(last_error, str) and ":" in str(last_error):
            detailed_error = last_error
        else:
            detailed_error = str(last_error) if last_error else "Unknown error"
        
        raise RuntimeError(f"API request failed after {retry_count} attempts: {detailed_error}")
    
    def get_templates(
        self,
        include_endpoint_bound: bool = False,
        include_public: bool = False,
        include_runpod: bool = False
    ) -> List[Template]:
        """Get list of templates."""
        params = {
            "includeEndpointBoundTemplates": include_endpoint_bound,
            "includePublicTemplates": include_public,
            "includeRunpodTemplates": include_runpod
        }
        
        response = self._request("GET", "/templates", params=params)
        
        templates = []
        for t in response:
            templates.append(Template(
                id=t.get("id", ""),
                name=t.get("name", "Unknown"),
                image_name=t.get("imageName", "Unknown"),
                container_disk_in_gb=t.get("containerDiskInGb", 0),
                volume_in_gb=t.get("volumeInGb", 0),
                ports=t.get("ports", []),
                is_serverless=t.get("isServerless", False)
            ))
        
        return templates
    
    def get_network_volumes(self) -> List[NetworkVolume]:
        """Get list of network volumes."""
        response = self._request("GET", "/networkvolumes")
        
        volumes = []
        for v in response:
            volumes.append(NetworkVolume(
                id=v.get("id", ""),
                name=v.get("name", "Unknown"),
                size=v.get("size", 0),
                data_center_id=v.get("dataCenterId", "")
            ))
        
        return volumes
    
    def get_pods(self) -> List[Pod]:
        """Get list of all pods."""
        response = self._request("GET", "/pods")
        
        pods = []
        for p in response:
            pods.append(Pod(
                id=p.get("id", ""),
                name=p.get("name", "Unknown"),
                status=p.get("desiredStatus", "UNKNOWN"),
                image=p.get("image", "Unknown"),
                public_ip=p.get("publicIp"),
                port_mappings=p.get("portMappings", {}),
                gpu=p.get("gpu"),
                network_volume_id=p.get("networkVolume", {}).get("id") if p.get("networkVolume") else None,
                template_id=p.get("templateId")
            ))
        
        return pods
    
    def get_pod(self, pod_id: str) -> Pod:
        """Get specific pod details."""
        response = self._request("GET", f"/pods/{pod_id}")
        
        return Pod(
            id=response.get("id", ""),
            name=response.get("name", "Unknown"),
            status=response.get("desiredStatus", "UNKNOWN"),
            image=response.get("image", "Unknown"),
            public_ip=response.get("publicIp"),
            port_mappings=response.get("portMappings", {}),
            gpu=response.get("gpu"),
            network_volume_id=response.get("networkVolume", {}).get("id") if response.get("networkVolume") else None,
            template_id=response.get("templateId")
        )
    
    def create_pod(
        self,
        name: str,
        template_id: Optional[str],
        network_volume_id: Optional[str],
        gpu_type_ids: List[str],
        gpu_count: int,
        cloud_type: str = "SECURE",
        ports: Optional[List[str]] = None,
        min_vram_gb: int = 24,
        support_public_ip: bool = True,
        is_spot: bool = False
    ) -> Pod:
        """Create a new pod."""
        
        # Ensure SSH port is always included if ports are provided
        final_ports = None
        if ports:
            final_ports = set(ports)
            final_ports.add("22/tcp")
            final_ports = list(final_ports)

        data = {
            "name": name,
            "cloudType": cloud_type,
            "computeType": "GPU",
            "gpuTypeIds": gpu_type_ids,
            "gpuCount": gpu_count,
            "supportPublicIp": support_public_ip,
            "interruptible": is_spot
        }
        
        if final_ports:
             data["ports"] = final_ports

        if template_id:
            data["templateId"] = template_id
        
        if network_volume_id:
            data["networkVolumeId"] = network_volume_id
        
        response = self._request("POST", "/pods", data=data)
        
        return Pod(
            id=response.get("id", ""),
            name=response.get("name", "Unknown"),
            status=response.get("desiredStatus", "UNKNOWN"),
            image=response.get("image", "Unknown"),
            public_ip=response.get("publicIp"),
            port_mappings=response.get("portMappings", {}),
            gpu=response.get("gpu"),
            network_volume_id=response.get("networkVolume", {}).get("id") if response.get("networkVolume") else None,
            template_id=response.get("templateId")
        )
    
    def delete_pod(self, pod_id: str) -> bool:
        """Delete a pod."""
        self._request("DELETE", f"/pods/{pod_id}")
        return True
    
    def _query_graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute GraphQL query."""
        url = "https://api.runpod.io/graphql"
        
        # RunPod GraphQL expects api_key as a query parameter
        params = {"api_key": self.api_key}
        
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
            
        response = self.session.post(url, params=params, json=payload, timeout=30)
        
        if response.status_code != 200:
            raise RuntimeError(f"GraphQL request failed: {response.status_code} {response.text}")
            
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
            
        return data

    def get_gpu_types(self, datacenter_id: Optional[str] = None, cloud_type: str = "SECURE") -> tuple[List[GPUInfo], Dict[str, int]]:
        """
        Get available GPU types with pricing and availability from GraphQL API.
        
        Returns tuple of (all_gpus, available_gpus_dict) where:
        - all_gpus: List of all GPU types with pricing
        - available_gpus_dict: Dict mapping gpu_id -> max available count (0, 1, or 2)
        """
        # Query based on the "SecureGpuTypes" operation, fetching availability for 1x and 2x
        query = """
        query SecureGpuTypes($input1: GpuLowestPriceInput, $input2: GpuLowestPriceInput) {
          gpuTypes {
            id
            displayName
            memoryInGb
            securePrice
            communityPrice
            communitySpotPrice
            price1gpu: lowestPrice(input: $input1) {
              minimumBidPrice
              uninterruptablePrice
              stockStatus
              gpuTypeDatacenters {
                dataCenterId
                availability
              }
            }
            price2gpus: lowestPrice(input: $input2) {
              minimumBidPrice
              uninterruptablePrice
              stockStatus
              gpuTypeDatacenters {
                dataCenterId
                availability
              }
            }
          }
        }
        """
        
        is_secure = (cloud_type == "SECURE")
        
        # We query for specific datacenter availability if provided, otherwise generic
        variables = {
            "input1": {
                "gpuCount": 1,
                "secureCloud": is_secure,
                "dataCenterId": datacenter_id if datacenter_id else ""
            },
            "input2": {
                "gpuCount": 2,
                "secureCloud": is_secure,
                "dataCenterId": datacenter_id if datacenter_id else ""
            }
        }
        
        try:
            data = self._query_graphql(query, variables)
            
            gpus = []
            availability = {}
            
            for g in data["data"]["gpuTypes"]:
                # Filter out crazy outliers or incomplete data
                if not g.get("memoryInGb"):
                    continue
                
                gpu_id = g["id"]
                
                # Get stock status for 1x
                stock_status = None
                if g.get("price1gpu"):
                    stock_status = g.get("price1gpu", {}).get("stockStatus")

                gpus.append(GPUInfo(
                    id=gpu_id,
                    display_name=g["displayName"],
                    memory_in_gb=g["memoryInGb"],
                    secure_price=g.get("securePrice") or 0.0,
                    community_spot_price=g.get("communitySpotPrice"),
                    stock_status=stock_status
                ))
                
                # Check availability for 1x and 2x
                max_avail = 0
                
                if not is_secure:
                    # For Community Cloud, lowestPrice returns pricing (minimumBidPrice) but often empty gpuTypeDatacenters
                    # We rely on the existence of the price itself to indicate availability
                    
                    # Check 1x
                    lp1 = g.get("price1gpu")
                    if lp1 and (lp1.get("minimumBidPrice") or lp1.get("uninterruptablePrice")):
                         max_avail = 1
                    
                    # Check 2x
                    lp2 = g.get("price2gpus")
                    if lp2 and (lp2.get("minimumBidPrice") or lp2.get("uninterruptablePrice")):
                         max_avail = 2
                         
                else:
                    # For Secure Cloud, we must check datacenter availability
                    
                    # Check 1x
                    lp1 = g.get("price1gpu")
                    if lp1 and lp1.get("gpuTypeDatacenters"):
                        for dc_info in lp1["gpuTypeDatacenters"]:
                            if datacenter_id and dc_info["dataCenterId"] != datacenter_id:
                                continue
                            if dc_info.get("availability") == "AVAILABLE":
                                max_avail = 1
                                break
                                
                    # Check 2x (only if 1x was available, usually, but let's check independently)
                    lp2 = g.get("price2gpus")
                    if lp2 and lp2.get("gpuTypeDatacenters"):
                        for dc_info in lp2["gpuTypeDatacenters"]:
                            if datacenter_id and dc_info["dataCenterId"] != datacenter_id:
                                continue
                            if dc_info.get("availability") == "AVAILABLE":
                                max_avail = 2
                                break
                
                availability[gpu_id] = max_avail
                
            return gpus, availability
                
        except Exception as e:
            # Fallback or re-raise? For now, re-raise as this is critical
            raise RuntimeError(f"Failed to fetch GPU types: {e}")

    def get_pod_ssh_port_from_graphql(self, pod_id: str) -> Optional[int]:
        """
        Fetch the correct TCP SSH port for a pod using GraphQL.
        This resolves issues where REST API returns UDP port or overwrites mappings.
        """
        query = """
        query MyPods {
          myself {
            pods {
              id
              runtime {
                ports {
                  privatePort
                  publicPort
                  type
                }
              }
            }
          }
        }
        """
        
        try:
            data = self._query_graphql(query)
            pods = data.get("data", {}).get("myself", {}).get("pods", [])
            
            target_pod = next((p for p in pods if p.get("id") == pod_id), None)
            if not target_pod:
                return None
                
            runtime = target_pod.get("runtime", {})
            if not runtime:
                return None
                
            ports = runtime.get("ports", [])
            for p in ports:
                if p.get("privatePort") == 22 and p.get("type") == "tcp":
                    return p.get("publicPort")
            
            return None
            
        except Exception:
            return None

    

    def check_gpu_availability(
        self,
        gpu_type_id: str,
        datacenter_id: str
    ) -> bool:
        """
        Check if a GPU is available in a datacenter by creating a test deployment.
        
        This makes a minimal API call to test availability.
        Returns True if available, False otherwise.
        """
        import uuid
        
        test_pod_name = f"availability-test-{uuid.uuid4().hex[:8]}"
        
        try:
            self.create_pod(
                name=test_pod_name,
                template_id=None,
                network_volume_id=None,
                gpu_type_ids=[gpu_type_id],
                gpu_count=1,
                ports=["22/tcp"],
                min_vram_gb=24
            )
            
            self.delete_pod(test_pod_name)
            return True
        
        except RuntimeError as e:
            error_msg = str(e)
            if "GPU" in error_msg or "unavailable" in error_msg.lower():
                return False
            raise
