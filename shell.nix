{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python310.override {
    packageOverrides = self: super: {

      google-cloud-ndb = super.buildPythonPackage rec {
        pname = "google-cloud-ndb";
        version = "1.11.1";

        src = super.fetchPypi {
          inherit pname version;
          sha256 = "sha256-ooEt7uTNEumYeN5EbmpVSqNKj/60OCVM4HHiUT7FaYY=";
        };
        propagatedBuildInputs = [
          super.setuptools
          super.google-cloud-core
          self.google-cloud-datastore
          super.pymemcache
          super.redis
          super.pytz
          self.protobuf
        ];
        doCheck = false;
      };

      google-cloud-datastore = super.buildPythonPackage rec {
        pname = "google-cloud-datastore";
        version = "1.15.5";
        src = super.fetchPypi {
          inherit pname version;
          sha256 = "sha256-2tyhYxCIt6c38xHfh1dKQX8lTOcdapgIDzbzW9yWsw8=";
        };
        propagatedBuildInputs = [
          self.protobuf
          super.google-cloud-core
        ];
        doCheck = false;
      };

      protobuf = super.protobuf.override { protobuf = pkgs.protobuf3_20; };

      appengine-python-standard = super.buildPythonPackage rec {
        pname = "appengine-python-standard";
        version = "1.0.0";
        src = super.fetchPypi {
          inherit pname version;
          sha256 = "sha256-h/HLQC6Ez4oaFkW2Kkkwb0e+QSmUQVC0wrJD4igkkrk=";
        };
        propagatedBuildInputs = [
          super.requests
          self.protobuf
          super.attrs
          super.google-auth
          super.pillow
          super.pytz
          super.frozendict
          super.ruamel-yaml
          super.mock
        ];
      };
    };

  };

  pythonEnv = python.withPackages (ps: [
    ps.google-cloud-logging
    ps.google-cloud-ndb
    ps.appengine-python-standard
    ps.flask
  ]);


in pkgs.mkShell {
  buildInputs = with pkgs; [
    pythonEnv
    # google-app-engine-go-sdk  # dev_appserver.py is in here for some reason
    (google-cloud-sdk.withExtraComponents ([
      google-cloud-sdk.components.app-engine-python
      google-cloud-sdk.components.app-engine-python-extras
     ]))
    jre

  ];
}
