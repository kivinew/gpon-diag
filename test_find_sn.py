from core.olt import get_olt_connection, close_all
from diagnose import load_config, _load_olt_credentials

cfg = load_config()
olt_cfg = cfg['olts'][0]
host = olt_cfg['host']
username, password = _load_olt_credentials(olt_cfg)
olt = get_olt_connection(host, 23, username, password, 30)
olt.connect()
print('Connected')
loc = olt.find_ont_by_sn('48575443847BCE20')
print('Result:', loc)
close_all()