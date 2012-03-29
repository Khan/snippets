from configobj import ConfigObj

token = 0
proxy_server = 0
proxy_type = 0

def init_cfg(config_fname):
    cfg = ConfigObj(config_fname)
    global token, proxy_type, proxy_server
    token = cfg['token']
    proxy_server = cfg.get('proxy_server', 0)
    proxy_type = cfg.get('proxy_type', 0)
