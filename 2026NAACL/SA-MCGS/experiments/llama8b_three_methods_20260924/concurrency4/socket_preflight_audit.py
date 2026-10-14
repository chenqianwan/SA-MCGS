#!/usr/bin/env python3
"""Local ephemeral TCP test only; never touches the experiment's port or process."""
import errno,json,platform,socket,time
from pathlib import Path


def probe(port,reuse):
    with socket.socket() as sock:
        if reuse:sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:sock.bind(('127.0.0.1',port));return {'bound':True,'errno':None}
        except OSError as exc:return {'bound':False,'errno':exc.errno,'error':str(exc)}

listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
listener.bind(('127.0.0.1',0));listener.listen(1);port=listener.getsockname()[1]
live_without=probe(port,False);live_with=probe(port,True)
client=socket.socket();client.settimeout(2);client.connect(('127.0.0.1',port))
server_conn,_=listener.accept();server_conn.settimeout(2)
# Server is the active closer, leaving the server's TCP endpoint in TIME_WAIT.
server_conn.shutdown(socket.SHUT_WR)
assert client.recv(1)==b''
client.close()
assert server_conn.recv(1)==b''
server_conn.close();listener.close()
with socket.socket() as checker:
    checker.settimeout(1);connect_errno=checker.connect_ex(('127.0.0.1',port))
after_without=probe(port,False);after_with=probe(port,True)
assert not live_with['bound'] and not live_without['bound']
assert connect_errno!=0
assert after_without['errno']==errno.EADDRINUSE
assert after_with['bound']
report={'checked_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':platform.platform(),
    'scope':'local ephemeral TCP sockets only; no production port/node/process touched','ephemeral_port':port,
    'live_listener_plain_bind':live_without,'live_listener_reuseaddr_bind':live_with,
    'after_close_connect_errno':connect_errno,'after_close_plain_bind':after_without,
    'after_close_reuseaddr_bind':after_with,'passed':True,
    'conclusion':'An inactive port can reject plain bind because of recently closed TCP connections. SO_REUSEADDR allows the expected rebinding while still rejecting an existing live listener.',
    'minimal_fix':'Before the existing probe bind, set sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1). Do not set SO_REUSEPORT and do not suppress EADDRINUSE.',
    'production_cause_limit':'This reproduces the mechanism on the local OS; actual dgx100 port-state evidence is needed to identify cause of job395039.'}
Path(__file__).with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
