{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311Packages.requests
    python311Packages.rich
    python311Packages.pexpect
    python311Packages.netifaces
    python311Packages.litellm
    openssh
  ];

  shellHook = ''
    echo "RunPod automation environment ready"
    echo "Run: python main.py deploy"
    echo ""
    echo "SSH keys expected at: ~/.ssh/id_rsa or ~/.ssh/id_ed25519"
  '';
}
