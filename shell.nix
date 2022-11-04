{ pkgs ? import <nixpkgs> {} }:

with pkgs;

mkShell {
  buildInputs = [
    google-app-engine-go-sdk  # dev_appserver.py is in here for some reason
    (google-cloud-sdk.withExtraComponents ([
      google-cloud-sdk.components.app-engine-python
      google-cloud-sdk.components.app-engine-python-extras
     ]))
    jre

  ];
}
