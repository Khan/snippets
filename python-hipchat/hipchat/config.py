#!!from configobj import ConfigObj
import logging

token = 0
proxy_server = 0
proxy_type = 0

def init_cfg(config_fname):
    try:
        cfglines = open(config_fname).read().splitlines() # removes trailing \n
        cfg = dict(l.split(' = ') for l in cfglines)
    except IOError:
        logging.error('Unable to open %s; disabling HipChat' % config_fname)
        return
    global token, proxy_type, proxy_server
    token = cfg['token']
    proxy_server = cfg.get('proxy_server', 0)
    proxy_type = cfg.get('proxy_type', 0)
