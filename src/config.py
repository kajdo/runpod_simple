"""Configuration management for RunPod automation."""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Manages configuration from environment variables and SSH key detection."""

    def __init__(self, env_path: Optional[str] = None):
        self.env_path = env_path or self._find_env_file()
        self._load_dotenv()
        self.api_key = self._load_api_key()
        self.ssh_password = self._load_ssh_password()
        self.ssh_key_path = self._find_ssh_key()
    
    def _find_env_file(self) -> Optional[str]:
        """Find .env file in current or parent directories."""
        current = Path.cwd()
        for _ in range(5):
            env_file = current / ".env"
            if env_file.exists():
                return str(env_file)
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None
    
    def _load_api_key(self) -> str:
        """Load and validate RunPod API key."""
        api_key = os.getenv("RUNPOD_API_KEY")
        
        if not api_key:
            raise ValueError(
                "RUNPOD_API_KEY not found in environment.\n"
                "Create a .env file with RUNPOD_API_KEY=your_key_here\n"
                "Or set it via: export RUNPOD_API_KEY=your_key_here"
            )
        
        api_key = api_key.strip()
        
        if not api_key.startswith("rpa_"):
            raise ValueError(
                f"Invalid API key format. Expected to start with 'rpa_', got: {api_key[:10]}..."
            )
        
        return api_key
    
    def _load_dotenv(self) -> None:
        """Load .env file into environment variables."""
        if not self.env_path:
            return
        
        env_file = Path(self.env_path)
        if not env_file.exists():
            return
        
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
    
    def _load_ssh_password(self) -> Optional[str]:
        """Load SSH password from environment (optional)."""
        password = os.getenv("SSH_PASSWORD")
        return password.strip() if password else None
    
    def _find_ssh_key(self) -> Optional[str]:
        """Find available SSH key file."""
        home = Path.home()
        key_paths = [
            home / ".ssh" / "id_ed25519",
            home / ".ssh" / "id_rsa",
        ]
        
        for key_path in key_paths:
            if key_path.exists():
                return str(key_path)
        
        return None
    
    def get_default_template(self) -> Optional[str]:
        """Load DEFAULT_TEMPLATE from environment."""
        value = os.getenv("DEFAULT_TEMPLATE")
        return value.strip() if value else None
    
    def get_default_network_volume(self) -> Optional[str]:
        """Load DEFAULT_NETWORK_VOLUME from environment (may be 'null')."""
        value = os.getenv("DEFAULT_NETWORK_VOLUME")
        if not value:
            return None
        value = value.strip()
        return value if value.lower() != "null" else None
    
    def get_default_allow_two_gpus(self) -> Optional[bool]:
        """Load DEFAULT_ALLOW_TWO_GPUS from environment."""
        value = os.getenv("DEFAULT_ALLOW_TWO_GPUS")
        if not value:
            return None
        return value.strip().lower() == "true"
    
    def get_default_min_cost_per_hour(self) -> Optional[float]:
        """Load DEFAULT_MIN_COST_PER_HOUR from environment."""
        value = os.getenv("DEFAULT_MIN_COST_PER_HOUR")
        if not value:
            return None
        try:
            return float(value.strip())
        except ValueError:
            return None
    
    def get_default_max_cost_per_hour(self) -> Optional[float]:
        """Load DEFAULT_MAX_COST_PER_HOUR from environment."""
        value = os.getenv("DEFAULT_MAX_COST_PER_HOUR")
        if not value:
            return None
        try:
            return float(value.strip())
        except ValueError:
            return None
    
    def get_default_model(self) -> Optional[str]:
        """Load DEFAULT_MODEL from environment."""
        value = os.getenv("DEFAULT_MODEL")
        return value.strip() if value else None
    
    def get_default_preseed(self) -> Optional[bool]:
        """Load DEFAULT_PRESEED from environment."""
        value = os.getenv("DEFAULT_PRESEED")
        if not value:
            return None
        return value.strip().lower() == "true"
    
    def validate(self) -> tuple[bool, str]:
        """Validate configuration and return (is_valid, error_message)."""
        if not self.api_key:
            return False, "API key is required"
        
        if not self.ssh_key_path and not self.ssh_password:
            return (
                False,
                "SSH authentication required. Either add SSH key to ~/.ssh/ "
                "or set SSH_PASSWORD in .env"
            )
        
        return True, ""
    
    def __repr__(self) -> str:
        return (
            f"Config(api_key=***, ssh_key_path={self.ssh_key_path}, "
            f"has_password={'yes' if self.ssh_password else 'no'})"
        )
