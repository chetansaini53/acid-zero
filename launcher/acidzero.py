import glob,os,io,time,socket,subprocess,urllib.request,json,base64,re,struct,select,threading,math
from PIL import Image,ImageOps,ImageDraw,ImageFont
import numpy as np
try: import acid_wifiroles
except Exception: acid_wifiroles=None
THEMES={
 'dark':{'BG':(7,13,9),'PANEL':(14,22,15),'TILE':(12,19,13),'FG':(216,255,232),'ACC':(25,255,121),'DIM':(93,128,104),'LINE':(23,48,35),'BARBG':(10,17,11)},
 'light':{'BG':(236,242,238),'PANEL':(255,255,255),'TILE':(250,252,250),'FG':(20,40,28),'ACC':(8,158,74),'DIM':(116,140,124),'LINE':(212,226,218),'BARBG':(244,248,244)},
}
BG=PANEL=TILE=FG=ACC=DIM=LINE=BARBG=(0,0,0)
theme='dark'
def apply_theme(name):
    global BG,PANEL,TILE,FG,ACC,DIM,LINE,BARBG
    t=THEMES.get(name,THEMES['dark']); BG=t['BG']; PANEL=t['PANEL']; TILE=t['TILE']; FG=t['FG']; ACC=t['ACC']; DIM=t['DIM']; LINE=t['LINE']; BARBG=t['BARBG']
try: theme=(open('/home/pi/acid_theme').read().strip() or 'dark')
except Exception: theme='dark'
if theme not in THEMES: theme='dark'
apply_theme(theme)
def save_theme():
    try: open('/home/pi/acid_theme','w').write(theme)
    except Exception: pass
CAL=[480.0/2816.0,0.0,-663*480.0/2816.0,0.0,-320.0/2512.0,2948*320.0/2512.0]
try:
    _cv=[float(x) for x in open('/home/pi/acid_cal').read().split()]
    if len(_cv)==6: CAL=_cv
except Exception: pass
def save_cal():
    try: open('/home/pi/acid_cal','w').write(' '.join('%.6f'%v for v in CAL))
    except Exception: pass
def find_tft():
    for d in sorted(glob.glob('/sys/class/graphics/fb[0-9]*')):
        try: nm=open(d+'/name').read().strip().lower()
        except Exception: continue
        if 'ili9486' in nm or 'fb_ili' in nm: return d
    return None
TFT=None
while TFT is None:
    TFT=find_tft()
    if TFT is None: time.sleep(2)
W,H=[int(x) for x in open(TFT+'/virtual_size').read().strip().split(',')]
BPP=int(open(TFT+'/bits_per_pixel').read().strip())
FB='/dev/'+os.path.basename(TFT)
URL='http://127.0.0.1:8080/ui'
def mono(sz,bold=False):
    c=['/usr/share/fonts/truetype/dejavu/DejaVuSansMono%s.ttf'%('-Bold' if bold else '')]
    c+=glob.glob('/usr/share/fonts/**/DejaVuSansMono*.ttf',recursive=True)
    c+=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
    for p in c:
        try: return ImageFont.truetype(p,sz)
        except Exception: pass
    return ImageFont.load_default()
F_TIT=mono(16,True); F_NM=mono(15,True); F_SM=mono(12,True); F_TILE=mono(11,True); F_BIG=mono(18,True); F_XL=mono(26,True); F_TINY=mono(10)
def pack(c):
    if BPP==16:
        a=np.asarray(c,dtype=np.uint16)
        return (((a[...,0]>>3)<<11)|((a[...,1]>>2)<<5)|(a[...,2]>>3)).astype('<u2').tobytes()
    return c.convert('RGBA').tobytes()
def rr(d,box,fill=None,outline=None,w=1,r=8):
    try: d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=w)
    except Exception: d.rectangle(box,fill=fill,outline=outline)
def lt(d,x,cy,t,f,fill=None):
    if fill is None: fill=FG
    bb=d.textbbox((0,0),t,font=f); d.text((x,cy-(bb[3]-bb[1])/2-bb[1]),t,font=f,fill=fill); return x+(bb[2]-bb[0])
def ct(d,cx,cy,t,f,fill=None):
    if fill is None: fill=FG
    bb=d.textbbox((0,0),t,font=f); d.text((cx-(bb[2]-bb[0])/2,cy-(bb[3]-bb[1])/2-bb[1]),t,font=f,fill=fill)
def ic(d,k,cx,cy,col):
    if k=='wifi':
        d.arc((cx-12,cy-7,cx+12,cy+17),200,340,fill=col,width=2); d.arc((cx-7,cy-2,cx+7,cy+12),200,340,fill=col,width=2); d.ellipse((cx-2,cy+8,cx+2,cy+12),fill=col)
    elif k=='antenna':
        d.line((cx,cy-12,cx,cy+12),fill=col,width=2); d.arc((cx-9,cy-13,cx+9,cy+5),200,340,fill=col,width=2); d.arc((cx-4,cy-9,cx+4,cy+1),200,340,fill=col,width=2)
    elif k=='key':
        d.ellipse((cx-12,cy-12,cx-2,cy-2),outline=col,width=2); d.line((cx-5,cy-5,cx+11,cy+11),fill=col,width=2); d.line((cx+7,cy+7,cx+12,cy+2),fill=col,width=2)
    elif k=='router':
        rr(d,(cx-12,cy+2,cx+12,cy+12),outline=col,w=2,r=2); d.line((cx,cy+2,cx,cy-6),fill=col,width=2); d.line((cx,cy-6,cx-5,cy-11),fill=col,width=2); d.line((cx,cy-6,cx+5,cy-11),fill=col,width=2)
    elif k=='bt':
        d.line((cx-6,cy-7,cx+6,cy+7),fill=col,width=2); d.line((cx-6,cy+7,cx+6,cy-7),fill=col,width=2); d.line((cx,cy-12,cx+6,cy-7),fill=col,width=2); d.line((cx,cy+12,cx+6,cy+7),fill=col,width=2); d.line((cx,cy-12,cx,cy+12),fill=col,width=2)
    elif k=='radio':
        d.arc((cx-12,cy-10,cx+12,cy+14),210,330,fill=col,width=2); d.arc((cx-7,cy-5,cx+7,cy+9),210,330,fill=col,width=2); d.ellipse((cx-2,cy+6,cx+2,cy+10),fill=col)
    elif k=='wave':
        pts=[(cx-12+i,int(cy+7*math.sin(i/3.0))) for i in range(0,25)]; d.line(pts,fill=col,width=2)
    elif k=='remote':
        rr(d,(cx-7,cy-12,cx+7,cy+12),outline=col,w=2,r=3); d.ellipse((cx-1,cy-3,cx+1,cy-1),fill=col); d.ellipse((cx-1,cy+4,cx+1,cy+6),fill=col)
    elif k=='usb':
        d.line((cx,cy+12,cx,cy-12),fill=col,width=2); d.polygon([(cx-3,cy-8),(cx+3,cy-8),(cx,cy-12)],fill=col); d.ellipse((cx-2,cy+10,cx+2,cy+14),fill=col); d.line((cx,cy,cx-6,cy-4),fill=col,width=2)
    elif k=='ghost':
        d.pieslice((cx-11,cy-12,cx+11,cy+8),180,360,outline=col,width=2); d.line((cx-11,cy-2,cx-11,cy+10),fill=col,width=2); d.line((cx+11,cy-2,cx+11,cy+10),fill=col,width=2); d.line((cx-11,cy+10,cx-4,cy+6),fill=col,width=2); d.line((cx-4,cy+6,cx+1,cy+10),fill=col,width=2); d.line((cx+1,cy+10,cx+5,cy+6),fill=col,width=2); d.line((cx+5,cy+6,cx+11,cy+10),fill=col,width=2); d.ellipse((cx-6,cy-4,cx-3,cy-1),fill=col); d.ellipse((cx+3,cy-4,cx+6,cy-1),fill=col)
    elif k=='net':
        d.ellipse((cx-3,cy-12,cx+3,cy-6),outline=col,width=2); d.ellipse((cx-12,cy+6,cx-6,cy+12),outline=col,width=2); d.ellipse((cx+6,cy+6,cx+12,cy+12),outline=col,width=2); d.line((cx,cy-6,cx,cy-2),fill=col,width=2); d.line((cx,cy-2,cx-8,cy+6),fill=col,width=2); d.line((cx,cy-2,cx+8,cy+6),fill=col,width=2)
    elif k=='pin':
        d.ellipse((cx-9,cy-12,cx+9,cy+6),outline=col,width=2); d.polygon([(cx-6,cy+2),(cx+6,cy+2),(cx,cy+13)],fill=col); d.ellipse((cx-3,cy-6,cx+3,cy),fill=BG)
    elif k=='gear':
        d.ellipse((cx-6,cy-6,cx+6,cy+6),outline=col,width=2)
        for ang in range(0,360,45):
            a=math.radians(ang); d.line((cx+8*math.cos(a),cy+8*math.sin(a),cx+12*math.cos(a),cy+12*math.sin(a)),fill=col,width=2)
    elif k=='info':
        d.ellipse((cx-11,cy-11,cx+11,cy+11),outline=col,width=2); d.ellipse((cx-1,cy-6,cx+1,cy-4),fill=col); d.line((cx,cy-1,cx,cy+6),fill=col,width=2)
    elif k=='radar':
        d.arc((cx-12,cy-12,cx+12,cy+12),0,360,fill=col,width=2); d.arc((cx-6,cy-6,cx+6,cy+6),0,360,fill=col,width=1); d.line((cx,cy,cx+9,cy-9),fill=col,width=2); d.ellipse((cx+4,cy-8,cx+8,cy-4),fill=col)
    else:
        rr(d,(cx-10,cy-10,cx+10,cy+10),outline=col,w=2,r=3)
def ic_scaled(d,k,cx,cy,col,s=0.92):
    t=Image.new('RGBA',(60,60),(0,0,0,0)); td=ImageDraw.Draw(t)
    ic(td,k,30,30,col); n=max(1,int(60*s)); t=t.resize((n,n),Image.LANCZOS)
    d._image.paste(t,(int(cx-n/2),int(cy-n/2)),t)
APPS=[('WiFi','wifi',(25,200,121)),('Radar','radar',(70,180,235)),('Handshake','key',(230,180,40)),('Evil AP','router',(235,130,55)),('BLE Spam','bt',(30,200,230)),('BLE Scan','bt',(70,130,235)),('Sub-GHz','radio',(175,125,235)),('NFC/RFID','wave',(235,70,150)),('IR Remote','remote',(235,130,55)),('Bad USB','usb',(30,200,121)),('Pwnagotchi','ghost',(30,200,230)),('Packets','net',(225,180,40)),('Wardrive','pin',(30,200,121)),('Settings','gear',(140,155,180)),('About','info',(140,155,180))]
COLS=5; ROWS=3; GX=5; GY=98; CW=(W-10)/COLS; CH=(H-GY-22)/ROWS
CAL_TARGETS=[(44,46),(436,46),(436,274),(44,274)]
def memp():
    try:
        m={}
        for l in open('/proc/meminfo'):
            k,v=l.split(':',1); m[k]=int(v.split()[0])
        return int(100.0*(m['MemTotal']-m['MemAvailable'])/m['MemTotal'])
    except Exception: return 0
def temp():
    try: return int(int(open('/sys/class/thermal/thermal_zone0/temp').read())/1000)
    except Exception: return 0
def pwnd():
    try: return len(glob.glob('/home/pi/handshakes/*.pcap'))
    except Exception: return 0
def upt():
    try:
        s=int(float(open('/proc/uptime').read().split()[0])); h=s//3600; m=(s%3600)//60
        return '%dh%02d'%(h,m) if h else '%dm'%m
    except Exception: return '?'
_chan={'v':'-','t':0.0}
def chan():
    if time.time()-_chan['t']<2.0: return _chan['v']
    try:
        o=subprocess.check_output(['iw','dev','wlan0mon','info'],stderr=subprocess.DEVNULL,timeout=1).decode()
        m=re.search(r'channel (\d+)',o); _chan['v']=(m.group(1) if m else '-')
    except Exception: _chan['v']='-'
    _chan['t']=time.time(); return _chan['v']
_board={'v':None}
def board():
    if _board['v'] is not None: return _board['v']
    try:
        b=open('/proc/device-tree/model').read().replace('\x00','').strip(); _board['v']=b.replace('Raspberry Pi','Pi').replace(' Model',' ').replace(' Plus','+').replace(' Rev','  r')
    except Exception: _board['v']='Pi'
    return _board['v']
def ipaddr():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(0.5); s.connect(('8.8.8.8',53)); r=s.getsockname()[0]; s.close(); return r
    except Exception: return '-'
def net_up():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(0.6); s.connect(('1.1.1.1',53)); s.close(); return True
    except Exception: return False
def wifi_aps():
    try:
        req=urllib.request.Request('http://127.0.0.1:8081/api/session')
        req.add_header('Authorization','Basic '+base64.b64encode(b'pwnagotchi:pwnagotchi').decode())
        d=json.loads(urllib.request.urlopen(req,timeout=2).read()); out=[]
        for a in d.get('wifi',{}).get('aps',[]):
            cl=[(c.get('mac',''),(c.get('vendor') or '?'),c.get('rssi') or -99) for c in a.get('clients',[])]
            out.append((a.get('hostname') or '<hidden>',a.get('channel') or 0,a.get('rssi') or -99,(a.get('encryption') or '?'),len(cl),a.get('mac',''),cl))
        return out
    except Exception: return None
def bc_cmd(c):
    try:
        req=urllib.request.Request('http://127.0.0.1:8081/api/session',data=json.dumps({'cmd':c}).encode(),headers={'Authorization':'Basic '+base64.b64encode(b'pwnagotchi:pwnagotchi').decode(),'Content-Type':'application/json'})
        urllib.request.urlopen(req,timeout=4); return True
    except Exception: return False
def start_deauth(targets):
    global wifi_status,wifi_status_t
    try:
        open('/tmp/acid_deauth_targets','w').write('\n'.join(targets))
        try: os.remove('/tmp/acid_deauth_stop')
        except Exception: pass
        subprocess.Popen(['setsid','bash','/usr/local/bin/acid-deauth.sh'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        wifi_status='deauth %d AP targeted (2.4G)'%len(targets); wifi_status_t=time.time()
    except Exception: wifi_status='deauth start err'; wifi_status_t=time.time()
def stop_deauth():
    global wifi_status,wifi_status_t
    try: open('/tmp/acid_deauth_stop','w').write('1')
    except Exception: pass
    wifi_status='deauth stopped'; wifi_status_t=time.time()
def wifi_view():
    if not wifi_list: return []
    v=wifi_list
    if wifi_filter=='clients': v=[a for a in v if a[4]>0]
    if wifi_sort=='channel': v=sorted(v,key=lambda x:x[1])
    elif wifi_sort=='clients': v=sorted(v,key=lambda x:x[4],reverse=True)
    elif wifi_sort=='name': v=sorted(v,key=lambda x:x[0].lower())
    else: v=sorted(v,key=lambda x:x[2],reverse=True)
    return v
def do_connect(ssid,pw=''):
    global wifi_status,wifi_status_t
    try:
        cmd=['nmcli','dev','wifi','connect',ssid,'ifname','wlan1']
        if pw: cmd+=['password',pw]
        r=subprocess.run(cmd,timeout=30,capture_output=True)
        wifi_status=('connected '+ssid) if r.returncode==0 else 'connect failed (check pw)'
    except Exception: wifi_status='connect timeout'
    wifi_status_t=time.time()
EP_TPLS=['wifi','google','router','social']
def ep_start():
    global ep_run,ep_status,ep_status_t
    try:
        open('/tmp/acid_portal_template','w').write(ep_tpl)
        open('/tmp/acid_portal_attempts','w').write(str(ep_att))
        open('/tmp/acid_portal_passthrough','w').write('1' if ep_pass else '0')
        open('/tmp/acid_portal_ssid','w').write(ep_ssid)
        try: os.remove('/tmp/acid_portal_stop')
        except Exception: pass
        subprocess.Popen(['setsid','bash','/usr/local/bin/acid-evilportal.sh',ep_ssid,str(ep_ch)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        ep_run=True; ep_status='starting AP...'; ep_status_t=time.time()
    except Exception: ep_status='start error'; ep_status_t=time.time()
def ep_stop():
    global ep_run,ep_status,ep_status_t
    try: open('/tmp/acid_portal_stop','w').write('1')
    except Exception: pass
    ep_run=False; ep_status='stopping...'; ep_status_t=time.time()
def ep_running():
    try:
        pids=open('/tmp/acid_ep_pids').read().split()
        return any(os.path.exists('/proc/%s'%p) for p in pids if p)
    except Exception: return False
def ep_apif():
    ap='?'
    try:
        for ln in open('/tmp/acid_portal_run.log'):
            m=re.search(r' on (wlan\d+)',ln)
            if m: ap=m.group(1)
    except Exception: pass
    return ap
def ep_creds(n=4):
    try:
        ls=[l for l in open('/tmp/acid_portal_creds.log').read().split('\n') if l.strip()]
        return ls[-n:]
    except Exception: return []
def ep_ncreds():
    try: return sum(1 for l in open('/tmp/acid_portal_creds.log') if l.strip())
    except Exception: return 0
def ep_nclients():
    try: return len(set(l.split()[1] for l in open('/tmp/acid_portal_clients') if len(l.split())>1 and l.split()[1]!='10.0.0.1'))
    except Exception: return 0
def hs_captured():
    s=set()
    try:
        for f in os.listdir('/home/pi/handshakes'):
            if f.endswith('.pcap') or f.endswith('.cap'):
                m=re.findall(r'[0-9a-fA-F]{12}',f)
                if m: s.add(m[-1].lower())
    except Exception: pass
    return s
def hs_count():
    try: return len([f for f in os.listdir('/home/pi/handshakes') if f.endswith('.pcap') or f.endswith('.cap')])
    except Exception: return 0
def hs_start(bssid,ch,essid):
    global hs_status,hs_status_t,hs_run
    if hs_run and time.time()-hs_status_t<35:
        hs_status='hunt already running, wait...'; hs_status_t=time.time(); return
    try:
        open('/tmp/acid_hs_result','w').write('starting')
        subprocess.Popen(['setsid','bash','/usr/local/bin/acid-handshake.sh',bssid,str(ch),essid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        hs_run=True; hs_status='hunting %s ~30s'%essid[:16]; hs_status_t=time.time()
    except Exception: hs_status='hunt start err'; hs_status_t=time.time()
def hs_result():
    try: return open('/tmp/acid_hs_result').read().strip()
    except Exception: return ''
def hs_export():
    global hs_status,hs_status_t
    try:
        subprocess.Popen(['setsid','bash','-c','cd /home/pi/handshakes && f=$(ls *.pcap *.cap 2>/dev/null) && [ -n "$f" ] && hcxpcapngtool -o ALL_cracking.22000 $f >/tmp/acid_hs_export.log 2>&1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        hs_status='converting -> handshakes/ALL_cracking.22000'; hs_status_t=time.time()
    except Exception: hs_status='export err'; hs_status_t=time.time()
def ble_scan_start():
    global ble_status,ble_status_t
    try:
        subprocess.Popen(['setsid','python3','/usr/local/bin/acid-ble-scan.py','8'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        ble_status='scanning ~8s...'; ble_status_t=time.time()
    except Exception: ble_status='scan err'; ble_status_t=time.time()
def ble_devices(n=7,off=0):
    out=[]
    try:
        for l in open('/tmp/acid_ble_devices'):
            p=l.rstrip('\n').split('|')
            if len(p)>=4: out.append((p[0],p[1],p[2],p[3]))
    except Exception: pass
    return out[off:off+n]
def ble_dev_count():
    try: return sum(1 for l in open('/tmp/acid_ble_devices') if l.strip())
    except Exception: return 0
def ble_scanning():
    try: return open('/tmp/acid_ble_status').read().startswith('scanning')
    except Exception: return False
BLE_MODES=['sink','apple','android','samsung','windows']
BLE_DESC={'sink':'all types mixed (Apple+Android+Sam+Win)','apple':'Apple proximity (AirPods/TV popups)','android':'Google Fast Pair popups','samsung':'Samsung Buds/Watch popups','windows':'Windows Swift Pair popups'}
def ble_spam_start():
    global ble_status,ble_status_t,ble_spam_run
    try:
        try: os.remove('/tmp/acid_ble_spam_stop')
        except Exception: pass
        subprocess.Popen(['setsid','python3','/usr/local/lib/acid-ble/spam.py','300',ble_mode],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        ble_spam_run=True; ble_status='spam %s'%ble_mode; ble_status_t=time.time()
    except Exception: ble_status='spam err'; ble_status_t=time.time()
def ble_spam_stop():
    global ble_spam_run,ble_status,ble_status_t
    try: open('/tmp/acid_ble_spam_stop','w').write('1')
    except Exception: pass
    ble_spam_run=False; ble_status='spam stopped'; ble_status_t=time.time()
def ble_spam_running():
    try: return open('/tmp/acid_ble_spam_status').read().startswith('spamming')
    except Exception: return False
def ble_spam_sent():
    try:
        m=re.search(r'sent=(\d+)',open('/tmp/acid_ble_spam_status').read()); return m.group(1) if m else '0'
    except Exception: return '0'
KB_LOW=['1234567890','qwertyuiop','asdfghjkl','zxcvbnm']
KB_UP=['1234567890','QWERTYUIOP','ASDFGHJKL','ZXCVBNM']
KB_SYM=['1234567890','@#$_-+()&/','*!?~%^=\\|','.,\'":;/']
def kb_keys():
    rows=KB_SYM if kb_sym else (KB_UP if kb_shift else KB_LOW); keys=[]; ys=[80,126,172,218]
    for ri,row in enumerate(rows):
        n=len(row); xs=(W-n*46)//2; y=ys[ri]
        for ci,ch in enumerate(row): keys.append((ch,xs+ci*46,y,xs+ci*46+44,y+42,'c'))
    y=266
    keys.append(('shift',4,y,74,y+48,'shift'))
    keys.append((('abc' if kb_sym else '?12'),78,y,148,y+48,'sym'))
    keys.append(('space',152,y,308,y+48,'space'))
    keys.append(('del',312,y,360,y+48,'bksp'))
    keys.append(('esc',364,y,414,y+48,'cancel'))
    keys.append(('GO',418,y,476,y+48,'go'))
    return keys
_c={'i':0,'t':0}
def cpu():
    try:
        p=[int(x) for x in open('/proc/stat').readline().split()[1:]]
        idle=p[3]+(p[4] if len(p)>4 else 0); tot=sum(p); di=idle-_c['i']; dt=tot-_c['t']; _c['i']=idle; _c['t']=tot
        return max(0,min(100,int(100.0*(dt-di)/dt))) if dt>0 else 0
    except Exception: return 0
def map_touch(rx,ry):
    sx=CAL[0]*rx+CAL[1]*ry+CAL[2]; sy=CAL[3]*rx+CAL[4]*ry+CAL[5]
    return max(0,min(W-1,int(round(sx)))),max(0,min(H-1,int(round(sy))))
_tap={'t':0.0,'x':-1,'y':-1,'rx':0,'ry':0}
def find_touch():
    for e in sorted(glob.glob('/sys/class/input/event*')):
        try: n=open(e+'/device/name').read().strip().lower()
        except Exception: continue
        if 'ads7846' in n or 'touch' in n: return '/dev/input/'+os.path.basename(e)
    return '/dev/input/event0'
def touch_thread():
    SZ=struct.calcsize('llHHi')
    try: fd=os.open(find_touch(),os.O_RDONLY|os.O_NONBLOCK)
    except Exception: return
    rx=ry=-1; down=False; pts=[]
    while True:
        try:
            r,_,_=select.select([fd],[],[],1.0)
            if not r: continue
            data=os.read(fd,SZ*256)
            for off in range(0,len(data)-SZ+1,SZ):
                _,_,typ,code,val=struct.unpack('llHHi',data[off:off+SZ])
                if typ==3 and code==0: rx=val
                elif typ==3 and code==1: ry=val
                elif typ==0:
                    if down and 100<rx<4000 and 100<ry<4000: pts.append((rx,ry))
                elif typ==1 and code==330:
                    if val==1: down=True; pts=[]; rx=ry=-1
                    elif val==0:
                        down=False
                        if len(pts)>=3:
                            ps=pts[1:-1]
                            xs=sorted(p[0] for p in ps); ys=sorted(p[1] for p in ps)
                            mx=xs[len(xs)//2]; my=ys[len(ys)//2]
                            sx,sy=map_touch(mx,my); _tap['x']=sx; _tap['y']=sy; _tap['rx']=mx; _tap['ry']=my; _tap['t']=time.time()
        except Exception: time.sleep(0.5)
threading.Thread(target=touch_thread,daemon=True).start()
MOODS=['hunting wifi...','sniffing packets','got a handshake!','looking around','scanning channels','feeling cool B)']
face_img=None
dirty=True
pwn_src=None; pwn_src_t=0.0
def face_thread():
    # single fetch of the pwnagotchi /ui PNG: crops the face for the home banner AND caches the
    # full grayscale frame (pwn_src) so the Pwnagotchi app can mirror it without a second GET.
    global face_img,dirty,pwn_src,pwn_src_t
    while True:
        try:
            data=urllib.request.urlopen(URL,timeout=4).read()
            g=Image.open(io.BytesIO(data)).convert('L')
            pwn_src=g; pwn_src_t=time.time()
            face_img=ImageOps.colorize(g.crop((18,30,144,84)),black=PANEL,white=ACC).convert('RGB'); dirty=True  # full face expression centered (drops name/status; no left clip)
        except Exception: pass
        time.sleep(2.0)
def net_bg_thread():
    global cur_ip,net_state,dirty,ssh_iface,active_radio
    while True:
        try:
            ni=ipaddr(); ns=net_up(); si=ssh_uplink_iface()
            try: ar=open('/tmp/acid_active_radio').read().strip()
            except Exception: ar=''
            if ni!=cur_ip or ns!=net_state or si!=ssh_iface or ar!=active_radio: dirty=True
            cur_ip=ni; net_state=ns; ssh_iface=si; active_radio=ar
        except Exception: pass
        time.sleep(4.0)
def wifi_bg_thread():
    global wifi_list,wifi_focus,wifi_off,dirty
    while True:
        if screen in ('WiFi','WiFiClients','Handshake','Radar:nearby','Radar:eviltwin','Radar:all'):
            wl=wifi_aps()
            if wl is not None:
                wifi_list=wl; wifi_off=min(wifi_off,max(0,len(wl)-6))
                if wifi_focus: wifi_focus=next((a for a in wl if a[5]==wifi_focus[5]),wifi_focus)
                dirty=True
            time.sleep(2.5)
        else:
            time.sleep(0.4)
pwn_img=None; pwn_fail=0
def pwn_bg_thread():
    # mirror the LIVE pwnagotchi display: reuse the full /ui frame face_thread already fetched
    # (no duplicate GET), rescale to the TFT + colorize to the active theme. Only renders while
    # the Pwnagotchi app is open; re-renders only on a new frame (or after an entry reset).
    global pwn_img,pwn_fail,dirty
    last_render=0.0
    while True:
        if screen=='Pwnagotchi':
            try:
                src=pwn_src
                if src is not None and time.time()-pwn_src_t<3 and (pwn_src_t!=last_render or pwn_img is None):
                    sw,sh=src.size; aw,ah=464,H-56; sc=min(aw/sw,ah/sh)
                    im=src.resize((max(1,int(sw*sc)),max(1,int(sh*sc))),Image.LANCZOS)
                    pwn_img=ImageOps.colorize(im,black=BG,white=FG).convert('RGB')
                    pwn_fail=0; last_render=pwn_src_t; dirty=True
                elif src is None or time.time()-pwn_src_t>=3:
                    if pwn_fail==0: dirty=True
                    pwn_fail=min(pwn_fail+1,99)
            except Exception:
                if pwn_fail==0: dirty=True
                pwn_fail=min(pwn_fail+1,99)
            time.sleep(0.5)
        else:
            time.sleep(0.4)
def draw_pwnagotchi(d):
    topbar(d,'PWNAGOTCHI')
    fresh=(pwn_fail==0 and time.time()-pwn_src_t<3)
    d.ellipse((W-30,11,W-22,19),fill=((30,200,121) if fresh else (235,180,40)))
    if pwn_img is None:
        ct(d,W//2,155,('pwnagotchi web not reachable' if pwn_fail>2 else 'connecting to pwnagotchi...'),F_NM,DIM); return
    iw,ih=pwn_img.size; x=(W-iw)//2; y=34+((H-18-34)-ih)//2
    d._image.paste(pwn_img,(x,max(34,y)))
CONSENT_FLAG='/home/pi/acid_consent'
learn_topic=''
# Educational layer: per-technique "how it works" + "detect / defend". Tapping (i) on an
# app's top bar opens this. Acid Zero is a teaching tool - every offence is paired with a defence.
LEARN={
 'WiFi':{'how':['Scans 802.11 APs/clients via bettercap.','Deauth sends spoofed 802.11 management frames','telling a client it is disconnected - no auth needed.','Pre-WPA3 management frames are unauthenticated.'],
         'defend':['Use WPA3-SAE + 802.11w PMF (Protected Mgmt','Frames): deauth is then cryptographically ignored.','Watch for deauth floods; prefer wired / VPN on','untrusted RF. Old WPA2 APs stay vulnerable.']},
 'Evil AP':{'how':['Stands up a rogue AP with a familiar SSID and','a captive portal mimicking a login page.','DNS is hijacked so any URL hits the portal;','auto-joining clients can be phished for creds.'],
         'defend':['Never enter WiFi/email passwords on a captive','portal. Disable auto-join to open networks.','Verify SSID + certificate; use 802.1X / EAP-TLS.','Treat unexpected login pages as hostile.']},
 'Handshake':{'how':['Captures the WPA 4-way handshake or PMKID when','a client (re)joins - sometimes nudged by deauth.','The capture is taken offline to Hashcat (.22000)','for dictionary / brute-force on the passphrase.'],
         'defend':['Use a long random passphrase (15+ chars) or','WPA3-SAE, which resists offline cracking.','Watch for unexpected deauths (capture trigger).','Disable WPS; rotate keys periodically.']},
 'BLE Scan':{'how':['Passively reads BLE advertising packets.','Decodes vendor (Company-ID), name and Apple /','Fast-Pair model to identify nearby devices.','100% passive - no connection, read-only recon.'],
         'defend':['Keep MAC randomization on (most phones default).','Turn BLE off when not in use.','Wearables / earbuds leak device type + presence.','This screen itself IS a defensive recon tool.']},
 'BLE Spam':{'how':['Broadcasts crafted BLE advertisements that','trigger pairing / proximity popups (Apple, Google,','Samsung, Microsoft) via raw HCI, rotating MACs.','Demonstrates abuse of BLE advertising trust.'],
         'defend':['Keep your OS updated - popup rate-limits added.','Turn BLE off in crowded / untrusted areas.','Modern iOS/Android harden against fast-pair spam.','Detect via a rapid spoofed-advertisement flood.']},
 'Packets':{'how':['Read-only 802.11 frame sniff on the monitor radio.','Counts frame types, top talkers, probe leaks.','Probe requests reveal SSIDs a device remembers.','Pure passive - it never transmits.'],
         'defend':['Disable auto-join / saved-network probing.','Use a randomized MAC and avoid broadcasting probes.','Your probe-request SSID list is a location leak.']},
 'Pwnagotchi':{'how':['An AI agent that captures WPA handshakes as it','roams, using reinforcement learning.','This screen mirrors its live display.','It is the base OS Acid Zero runs on.'],
         'defend':['Same as Handshake: strong passphrase / WPA3.','Captured handshakes are useless if the key is','strong. Shows that passive capture is constant.']},
}
LEARN['Radar:all']={'how':['Runs every Radar detector in one pass: deauth flood,','BLE spam, Flipper presence, evil-twin. One shared','BLE scan + one sniffer feed all signals (no double','scan). Each row = OK / ALERT at a glance. Passive.'],
         'defend':['A single board to watch your own RF space.','Green = quiet; red = investigate that vector via its','dedicated detector screen. Never transmits.']}
LEARN['Radar:eviltwin']={'how':['Groups nearby APs by SSID. An "evil twin" clones a','known SSID on a different BSSID to lure clients -','classic tell = the SAME name appearing both OPEN and','secured. Flags duplicate SSIDs + encryption mismatch.'],
         'defend':['Connect only to known BSSIDs; verify the AP MAC.','Distrust an open network named like a secured one.','Use 802.1X / cert pinning; duplicate SSID alone can','be legit mesh - the open+secured mix is the red flag.']}
LEARN['Radar:flipper']={'how':['Flipper Zero advertises over BLE with a Local Name','starting "Flipper" and a custom serial GATT service','(8fe5b3d5-...). This passively flags that signature','+ RSSI (proximity). It does NOT see Sub-GHz/NFC use.'],
         'defend':['A Flipper nearby is not itself an attack - context','matters. Pair it with the Deauth / BLE-Spam / Sub-GHz','detectors to see if it is actually transmitting.']}
LEARN['Radar:blespam']={'how':['Passively watches BLE advertising for a flood of','pairing-popup spam (Apple ProximityPair/NearbyAction,','Google Fast Pair, Samsung, Microsoft) from many','rotating random MACs. Counts distinct MACs -> alert.'],
         'defend':['Keep phone OS updated (popup rate-limits).','Turn BLE off in crowded/untrusted areas.','Real devices = few MACs; spam = many new MACs fast.']}
LEARN['Radar:deauth']={'how':['Passively sniffs 802.11 deauth/disassoc frames on','the monitor radio (hops 2.4+5GHz). A flood = many','such frames forcing clients off-net. Counts + alerts;','never transmits. Shows attacked AP + target clients.'],
         'defend':['WPA3-SAE + 802.11w PMF -> deauth cryptographically','ignored. On WPA2 it works, so treat sudden mass','disconnects as an attack signal. Prefer 5GHz / wired.']}
LEARN['BLE Inspect']={'how':['Connects to a BLE device as a GATT client and','enumerates its services + characteristics (and a','few readable values: name, battery, maker).','Active - it makes a real connection, unlike Scan.'],
         'defend':['Require pairing/bonding + encryption on sensitive','characteristics (LE Secure Connections).','Don\'t leave device-info/credentials world-readable.','Use resolvable-private addresses + whitelists.']}
LEARN['Wardrive']={'how':['Reads bettercap\'s existing AP scan (same feed','WiFi Hunter uses - no second scanner spawned)','and tags each sighting with GPS coordinates.','Read-only: it never transmits, cracks, or joins.'],
         'defend':['This is standard site-survey / auditing practice.','Hide-SSID only deters casual discovery, not real','attackers. WPA3 protects the passphrase, not','whether the AP itself is visible on a public map.']}
def draw_consent(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    ct(d,W//2,15,'AUTHORIZED USE ONLY',F_TIT,(235,180,40))
    lines=['Acid Zero is an EDUCATIONAL security tool.','',
           'Use ONLY on devices / networks you OWN or have','WRITTEN authorization to test.','',
           'Unauthorized Wi-Fi deauth, rogue APs, or BLE','spam is ILLEGAL in most countries.','',
           'Tapping ACCEPT confirms authorized, educational','use - you accept full responsibility.']
    y=42
    for ln in lines: lt(d,18,y,ln[:54],F_SM,FG); y+=16
    rr(d,(90,258,390,296),fill=ACC,r=10); ct(d,240,277,'I UNDERSTAND & ACCEPT',F_NM,BG)
LEARN_VIS=13   # info lines visible before UP/DOWN paging kicks in
def draw_learn(d):
    global learn_off
    topbar(d,learn_topic[:18])
    info=LEARN.get(learn_topic,{})
    lines=[(14,'HOW IT WORKS',ACC)]
    for ln in info.get('how',[]): lines.append((20,ln[:54],FG))
    lines.append((0,'',FG))
    lines.append((14,'DETECT / DEFEND',(70,130,235)))
    for ln in info.get('defend',[]): lines.append((20,ln[:54],DIM))
    total=len(lines); maxoff=max(0,total-LEARN_VIS); learn_off=min(max(learn_off,0),maxoff)
    y=40
    for indent,txt,col in lines[learn_off:learn_off+LEARN_VIS]:
        if txt: lt(d,indent,y,txt,F_SM,col)
        y+=18
    if total>LEARN_VIS:
        by=H-24
        rr(d,(10,by,120,by+21),outline=LINE,w=1,r=6); ct(d,65,by+10,'UP',F_SM,FG if learn_off>0 else DIM)
        ct(d,240,by+10,'%d-%d / %d'%(learn_off+1,min(learn_off+LEARN_VIS,total),total),F_TINY,DIM)
        rr(d,(360,by,470,by+21),outline=LINE,w=1,r=6); ct(d,415,by+10,'DOWN',F_SM,FG if learn_off<maxoff else DIM)
    else:
        lt(d,14,H-28,'educational / authorized use only',F_TINY,DIM)
def learn_btn(d):
    # the (i) info button next to '< back' on any screen that has a LEARN entry
    if screen in LEARN:
        rr(d,(98,4,144,24),outline=(70,130,235),w=1,r=5); ct(d,121,15,'(i)',F_SM,(70,130,235))
def topbar(d,title):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC)
    ct(d,W//2,15,title,F_TIT,FG); learn_btn(d)
grid_cache=None; grid_cache_theme=None; grid_cache_page=-1
def build_grid(page=0):
    gi=Image.new('RGB',(W,max(1,H-GY)),BG); gd=ImageDraw.Draw(gi); gd._image=gi
    per=COLS*ROWS
    tiles=GRID[page*per:(page+1)*per]
    for i,(nm,k,col) in enumerate(tiles):
        cx0=GX+(i%COLS)*CW; cy0=(i//COLS)*CH; box=(cx0+3,cy0+3,cx0+CW-3,cy0+CH-3)
        rr(gd,box,fill=TILE,outline=LINE,w=1,r=10); cx=(box[0]+box[2])//2
        ic_scaled(gd,k,cx,cy0+22,col); ct(gd,cx,cy0+CH-15,nm[:9],F_TILE,FG)
    return gi
def draw_home(d,mi):
    d.rectangle((0,0,W,26),fill=BARBG); d.line([(0,26),(W,26)],fill=LINE)
    x=lt(d,9,13,'ACID',F_TIT,ACC); x=lt(d,x+8,13,'// zero',F_SM,DIM)
    ct(d,240,13,time.strftime('%H:%M   %a %d'),F_SM,FG)   # clock centered (page indicator moved to footer)
    rs='CPU '+str(cpu())+'%  CH '+str(chan())+'  '+str(temp())+'°  '+str(memp())+'%'
    bb=d.textbbox((0,0),rs,font=F_SM); lt(d,W-10-(bb[2]-bb[0]),13,rs,F_SM,DIM)
    d.rectangle((0,27,W,93),fill=PANEL); d.line([(0,94),(W,94)],fill=LINE)
    rr(d,(6,31,128,90),fill=TILE,outline=LINE,w=1,r=8)
    if face_img is not None:
        iw,ih=face_img.size; s=min(122/iw,59/ih)*0.8; fw=max(1,int(iw*s)); fh=max(1,int(ih*s))   # fit box, then 20% smaller
        d._image.paste(face_img.resize((fw,fh),Image.NEAREST),(6+(122-fw)//2,31+(59-fh)//2))   # horiz + vert center
    lt(d,140,46,'acid',F_NM,FG); rr(d,(178,39,224,54),outline=ACC,w=1,r=4); ct(d,201,46,'AUTO',F_SM,ACC)
    lt(d,140,70,MOODS[mi],F_SM,DIM)
    ct(d,300,46,str(pwnd()),F_BIG,ACC); ct(d,300,68,'pwnd',F_SM,DIM)
    ct(d,400,46,upt(),F_BIG,ACC); ct(d,400,68,'uptime',F_SM,DIM)
    global grid_cache,grid_cache_theme,grid_cache_page
    if grid_cache is None or grid_cache_theme!=theme or grid_cache_page!=home_page:
        grid_cache=build_grid(home_page); grid_cache_theme=theme; grid_cache_page=home_page
    d._image.paste(grid_cache,(0,GY))
def draw_about(d):
    topbar(d,'ABOUT')
    ct(d,W//2,46,'ACID ZERO',F_BIG,ACC); ct(d,W//2,64,'v0.1  ·  pentest handheld',F_TINY,DIM)
    if face_img is not None:
        fw=76; fh=int(face_img.size[1]*fw/face_img.size[0]); d._image.paste(face_img.resize((fw,fh),Image.NEAREST),(24,80))
    rr(d,(116,80,340,116),fill=TILE,outline=LINE,w=1,r=8); ct(d,228,94,'author',F_TINY,DIM); ct(d,228,106,'Chetan Saini',F_SM,ACC)
    rows=[('board',board()),('ip',ipaddr()),('uptime',upt()),('pwned',str(pwnd())+' handshakes')]
    y=138
    for k,v in rows:
        lt(d,40,y,k,F_SM,DIM); lt(d,150,y,str(v)[:36],F_SM,FG); y+=19
    rr(d,(10,244,232,286),fill=TILE,outline=ACC,w=2,r=10); ct(d,121,265,'HARDWARE INFO  >',F_SM,ACC)
    rr(d,(248,244,470,286),fill=TILE,outline=(70,130,235),w=2,r=10); ct(d,359,260,'PORTING REF  >',F_SM,(120,180,255)); ct(d,359,276,'CC1101/PN532/Flipper',F_TINY,DIM)
hw_lines=[]
def hwinfo_collect():
    global hw_lines
    def sh(c):
        try: return subprocess.run(['bash','-c',c],capture_output=True,timeout=4).stdout.decode('utf-8','replace').strip()
        except Exception: return ''
    bt=sh("hciconfig 2>/dev/null|awk '/BD Address/{print $3}'|head -1") or '-'
    ifs=sh("ls /sys/class/net|grep -E '^wlan'").split()
    rad=[]
    for w in ifs:
        drv=sh("basename $(readlink /sys/class/net/%s/device/driver 2>/dev/null)"%w) or '?'
        rad.append('%s:%s'%(w,drv))
    radtxt=['  '.join(rad[i:i+2]) for i in range(0,len(rad),2)]
    L=[('board',(sh("cat /proc/device-tree/model|tr -d '\\0'") or 'Pi 3B+')[:30]),
       ('kernel',sh('uname -m')+'  '+sh('uname -r').split('+')[0]),
       ('display','ILI9486 480x320 RGB565 16bpp'),
       ('disp bus','SPI0 16MHz rot270 (piscreen)'),
       ('fb / touch','/dev/fb1  +  ADS7846 event0'),
       ('bluetooth','hci0 UART '+bt),
       ('free bus','I2C-1, I2C-2  (SPI0=TFT)'),
       ('radios','%d wlan ifaces'%len(ifs))]
    for t in radtxt: L.append((' ',t))
    hw_lines=L
def draw_hwinfo(d):
    topbar(d,'HARDWARE INFO')
    if not hw_lines:
        ct(d,W//2,150,'reading hardware...',F_NM,DIM); return
    y=40
    for k,v in hw_lines:
        lt(d,16,y,k,F_SM,(DIM if k==' ' else ACC)); lt(d,150,y,str(v)[:42],F_SM,FG); y+=20
    rr(d,(10,286,470,314),fill=TILE,outline=(70,130,235),w=2,r=8)
    ct(d,240,300,'VIEW PORTING REFERENCE  (CC1101 / PN532 / Flipper)  >',F_TINY,(120,180,255))
# ---- on-device Porting Reference viewer (renders acid-hwref.py's content, same as the PDF) ----
hwref_blocks=None; hwref_flat=[]; hwref_page=0; HWREF_PER=14
def _hw_wrap(s,n):
    out=[]
    for para in s.split('\n'):
        if not para: out.append(''); continue
        w=''
        for word in para.split(' '):
            if len(w)+len(word)+1<=n: w=(w+' '+word).strip()
            else:
                if w: out.append(w)
                while len(word)>n: out.append(word[:n]); word=word[n:]
                w=word
        out.append(w)
    return out
def hwref_load():
    global hwref_blocks,hwref_flat
    try:
        import importlib.util as _ilu
        spec=_ilu.spec_from_file_location('acidhwref','/usr/local/bin/acid-hwref.py')
        m=_ilu.module_from_spec(spec); spec.loader.exec_module(m)
        B=m.content(m.live())
    except Exception as e:
        B=[('h1','REFERENCE UNAVAILABLE'),('b','could not load acid-hwref.py:'),('b',str(e)[:52])]
    flat=[]
    for kind,txt in B:
        if kind in ('sp','rule'): flat.append((0,'',kind)); continue
        ind=14 if kind=='h1' else 22 if kind=='h2' else 26
        for wl in _hw_wrap(txt,54 if kind in ('h1','h2','b') else 58): flat.append((ind,wl,kind))
    hwref_flat=flat; hwref_blocks=B
def draw_hwref(d):
    global hwref_page
    topbar(d,'PORTING REFERENCE')
    if hwref_blocks is None:
        ct(d,W//2,150,'building reference...',F_NM,DIM); ct(d,W//2,172,'reading live hardware (~6s)',F_SM,DIM); return
    total=max(1,(len(hwref_flat)+HWREF_PER-1)//HWREF_PER); hwref_page=min(max(hwref_page,0),total-1)
    start=hwref_page*HWREF_PER; y=36
    for x,txt,kind in hwref_flat[start:start+HWREF_PER]:
        if kind=='rule': d.line([(14,y+8),(W-14,y+8)],fill=LINE)
        elif txt:
            col=ACC if kind=='h1' else (70,130,235) if kind=='h2' else (150,200,150) if kind=='m' else FG
            lt(d,x,y,txt[:60],F_SM,col)
        y+=18
    by=H-24
    rr(d,(10,by,120,by+21),outline=LINE,w=1,r=6); ct(d,65,by+10,'< PREV',F_SM,FG if hwref_page>0 else DIM)
    ct(d,240,by+10,'%d / %d'%(hwref_page+1,total),F_SM,FG)
    rr(d,(360,by,470,by+21),outline=LINE,w=1,r=6); ct(d,415,by+10,'NEXT >',F_SM,FG if hwref_page<total-1 else DIM)
def hwref_open():
    global hwref_page,screen
    hwref_page=0; screen='hwref'
    if hwref_blocks is None: threading.Thread(target=hwref_load,daemon=True).start()
RADAR_SUBS=[('All Watch','all','active'),('Nearby Devices','nearby','active'),('Deauth Detector','deauth','active'),('BLE Spam Detector','blespam','active'),('Flipper Detector','flipper','active'),('Evil-Twin Detector','eviltwin','active')]
RADAR_DESC={'all':'every detector at once','nearby':'WiFi + BLE devices around you','deauth':'deauth/disassoc flood (2.4+5G)','blespam':'BLE advertising spam flood','flipper':'Flipper Zero presence + BLE spam','eviltwin':'rogue AP / evil twin'}
RADAR_CW=(W-16)//2; RADAR_Y0=54; RADAR_CH=80
def draw_radar(d):
    topbar(d,'RADAR')
    ct(d,W//2,40,'defensive detection  -  alert mode, no attack',F_SM,DIM)
    for i,(name,key,stt) in enumerate(RADAR_SUBS):
        c=i%2; r=i//2; bx=8+c*RADAR_CW; by=RADAR_Y0+r*RADAR_CH; cx=bx+RADAR_CW//2
        act=(stt=='active')
        rr(d,(bx+4,by+4,bx+RADAR_CW-4,by+RADAR_CH-6),fill=TILE,outline=(ACC if act else LINE),w=(2 if act else 1),r=10)
        ct(d,cx,by+22,name,F_NM,(FG if act else DIM))
        ct(d,cx,by+42,RADAR_DESC.get(key,'')[:32],F_TINY,DIM)
        ct(d,cx,by+62,'OPEN' if act else 'SOON',F_SM,(ACC if act else (120,130,150)))
RADAR_CX,RADAR_CY,RADAR_R=120,182,92
def draw_radar_nearby(d):
    global radar_sweep,radar_img,radar_img_t,radar_img_theme
    cx,cy,R=RADAR_CX,RADAR_CY,RADAR_R
    if radar_img is None or radar_img_theme!=theme or time.time()-radar_img_t>1.5:   # static layer cached; rebuild on data/theme change
        aps=wifi_list or []; bdevs=ble_devices(40)
        ri=Image.new('RGB',(W,H),BG); rd=ImageDraw.Draw(ri); rd._image=ri
        topbar(rd,'RADAR // NEARBY')
        ct(rd,W//2,40,'WiFi %d   BLE %d   %s'%(len(aps),len(bdevs),'scanning' if ble_scanning() else ''),F_SM,DIM)
        for k in (R,int(R*0.66),int(R*0.33)): rd.ellipse((cx-k,cy-k,cx+k,cy+k),outline=LINE,width=1)
        rd.line((cx-R,cy,cx+R,cy),fill=LINE); rd.line((cx,cy-R,cx,cy+R),fill=LINE)
        def place(rssi,key):
            try: rv=int(rssi)
            except Exception: rv=-99
            norm=max(0.0,min(1.0,(rv+95)/65.0)); rad=R*(1.0-norm)+5
            ang=math.radians(hash(str(key))%360); return cx+rad*math.cos(ang),cy+rad*math.sin(ang)
        for ap in aps:
            x,yy=place(ap[2],ap[5] or ap[0]); rd.ellipse((x-3,yy-3,x+3,yy+3),fill=(30,200,121))
        for mac,rssi,atype,lbl in bdevs:
            x,yy=place(rssi,mac); rd.rectangle((x-2,yy-2,x+2,yy+2),fill=(70,130,235))
        ct(rd,cx,cy+R+10,'green=WiFi  blue=BLE',F_TINY,DIM)
        merged=[(ap[2],'W',ap[0] or '<hidden>') for ap in aps]+[(rssi,'B',lbl or mac) for mac,rssi,atype,lbl in bdevs]
        def _rv(x):
            try: return int(x[0])
            except Exception: return -99
        merged.sort(key=_rv,reverse=True)
        x0=246; y=62; lt(rd,x0,46,'closest:',F_TINY,DIM)
        for rssi,t,name in merged[:13]:
            c=(30,200,121) if t=='W' else (70,130,235); rd.ellipse((x0,y+3,x0+7,y+10),fill=c)
            lt(rd,x0+13,y+2,str(name)[:22],F_TINY,FG); lt(rd,W-40,y+2,str(rssi),F_TINY,DIM); y+=18
        radar_img=ri; radar_img_t=time.time(); radar_img_theme=theme
    d._image.paste(radar_img,(0,0))
    radar_sweep=(radar_sweep+7)%360; a=math.radians(radar_sweep)   # only the sweep is per-frame
    d.line((cx,cy,int(cx+R*math.cos(a)),int(cy+R*math.sin(a))),fill=ACC,width=2)
def _radar_read(p):
    try: return [l for l in open(p).read().split('\n') if l]
    except Exception: return []
def radar_deauth_start():
    try: os.remove('/tmp/acid_radar_deauth_stop')
    except Exception: pass
    try: open('/tmp/acid_radar_deauth','w').write('count=0 rate=0 alert=0 iface=wlan0mon band=- max=0 dur=0')
    except Exception: pass
    try: subprocess.Popen(['setsid','python3','/usr/local/bin/acid-deauth-detect.py'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def radar_deauth_stop():
    try: open('/tmp/acid_radar_deauth_stop','w').write('1')
    except Exception: pass
def draw_radar_deauth(d):
    topbar(d,'DEAUTH DETECTOR')
    kv={}; aps=[]; tgts=[]
    for i,l in enumerate(_radar_read('/tmp/acid_radar_deauth')):
        if i==0:
            for tok in l.split():
                if '=' in tok: k,v=tok.split('=',1); kv[k]=v
        else:
            p=l.split('|')
            if p[0]=='B' and len(p)>2: aps.append((p[1],p[2]))
            elif p[0]=='T' and len(p)>2: tgts.append((p[1],p[2]))
    alert=kv.get('alert')=='1'
    if alert:
        rr(d,(10,34,W-10,74),fill=(120,20,20),outline=(235,80,80),w=2,r=8)
        ct(d,W//2,48,'!!  DEAUTH FLOOD DETECTED  !!',F_NM,(255,190,190))
        ct(d,W//2,64,'%s frames/5s  on %s GHz'%(kv.get('count','0'),kv.get('band','-')),F_SM,(255,215,215))
    else:
        rr(d,(10,34,W-10,74),fill=PANEL,outline=ACC,w=1,r=8)
        ct(d,W//2,48,'MONITORING  -  no flood',F_NM,ACC)
        ct(d,W//2,64,'passive watch on %s'%kv.get('iface','wlan0mon'),F_SM,DIM)
    lt(d,16,88,'count(5s): %s    rate: %s/s    peak: %s/s'%(kv.get('count','0'),kv.get('rate','0'),kv.get('max','0')),F_SM,FG)
    lt(d,16,106,'bands: %s GHz    watching: %ss'%(kv.get('band','-'),kv.get('dur','0')),F_SM,DIM)
    d.line([(10,126),(W-10,126)],fill=LINE)
    lt(d,16,134,'attacked APs (BSSID):',F_SM,(235,180,40)); y=152
    for mac,n in aps[:3]: lt(d,26,y,'%s    x%s'%(mac,n),F_SM,FG); y+=18
    if not aps: lt(d,26,y,'-',F_SM,DIM); y+=18
    y+=6; lt(d,16,y,'targets (clients):',F_SM,(70,130,235)); y+=18
    for mac,n in tgts[:3]: lt(d,26,y,'%s    x%s'%(mac,n),F_SM,FG); y+=18
    if not tgts: lt(d,26,y,'- (or broadcast ff:ff:..)',F_SM,DIM); y+=18
    lt(d,16,H-30,'alert-only: detects deauth/disassoc, never transmits',F_TINY,DIM)
def radar_blespam_start():
    try: os.remove('/tmp/acid_radar_blespam_stop')
    except Exception: pass
    try: open('/tmp/acid_radar_blespam','w').write('count=0 macs=0 alert=0 dur=0 max=0')
    except Exception: pass
    try: subprocess.Popen(['setsid','python3','/usr/local/bin/acid-blespam-detect.py'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def radar_blespam_stop():
    try: open('/tmp/acid_radar_blespam_stop','w').write('1')
    except Exception: pass
def draw_radar_blespam(d):
    topbar(d,'BLE SPAM DETECTOR')
    kv={}; vend=[]
    for i,l in enumerate(_radar_read('/tmp/acid_radar_blespam')):
        if i==0:
            for tok in l.split():
                if '=' in tok: k,v=tok.split('=',1); kv[k]=v
        else:
            p=l.split('|')
            if p[0]=='V' and len(p)>2: vend.append((p[1],p[2]))
    alert=kv.get('alert')=='1'
    if alert:
        rr(d,(10,34,W-10,74),fill=(120,20,20),outline=(235,80,80),w=2,r=8)
        ct(d,W//2,48,'!!  BLE SPAM FLOOD DETECTED  !!',F_NM,(255,190,190))
        ct(d,W//2,64,'%s distinct spoofed devices / 5s'%kv.get('macs','0'),F_SM,(255,215,215))
    else:
        rr(d,(10,34,W-10,74),fill=PANEL,outline=ACC,w=1,r=8)
        ct(d,W//2,48,'MONITORING  -  no spam',F_NM,ACC)
        ct(d,W//2,64,'passive BLE advertising watch',F_SM,DIM)
    lt(d,16,88,'distinct MACs(5s): %s    adv: %s    peak: %s'%(kv.get('macs','0'),kv.get('count','0'),kv.get('max','0')),F_SM,FG)
    lt(d,16,106,'watching: %ss   threshold: 12 MACs/5s'%kv.get('dur','0'),F_SM,DIM)
    d.line([(10,126),(W-10,126)],fill=LINE)
    lt(d,16,134,'spam by vendor (distinct MACs):',F_SM,(235,180,40)); y=156
    cols={'Apple':(220,220,225),'FastPair':(70,180,235),'Samsung':(70,130,235),'Microsoft':(120,200,255)}
    if vend:
        for name,n in vend:
            lt(d,26,y,'%-12s'%name,F_NM,cols.get(name,FG)); lt(d,210,y,'x%s'%n,F_NM,FG); y+=24
    else:
        lt(d,26,y,'none',F_SM,DIM)
    lt(d,16,H-30,'alert-only: detects pairing-popup spam, never sends',F_TINY,DIM)
def radar_all_start():
    try: os.remove('/tmp/acid_radar_all_stop')
    except Exception: pass
    try: open('/tmp/acid_radar_all','w').write('deauth_count=0 deauth_alert=0 deauth_band=-\nble_macs=0 ble_alert=0\nflipper_count=0 flipper_alert=0\nble_total=0 iface=- dur=0')
    except Exception: pass
    try: subprocess.Popen(['setsid','python3','/usr/local/bin/acid-radar-all.py'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def radar_all_stop():
    try: open('/tmp/acid_radar_all_stop','w').write('1')
    except Exception: pass
def draw_radar_all(d):
    topbar(d,'ALL WATCH')
    kv={}
    for l in _radar_read('/tmp/acid_radar_all'):
        for tok in l.split():
            if '=' in tok: k,v=tok.split('=',1); kv[k]=v
    aps=wifi_list or []; groups={}
    for ap in aps:
        s=ap[0]
        if s and s!='<hidden>': groups.setdefault(s,[]).append(ap)
    et_sus=0; et_dup=0
    for s,lst in groups.items():
        b={a[5] for a in lst if a[5]}
        if len(b)<2: continue
        up=[(a[3] or '?').upper() for a in lst]
        sec=any(('WPA' in e or 'WEP' in e) for e in up); ins=any(not('WPA' in e or 'WEP' in e) for e in up)
        if sec and ins: et_sus+=1
        else: et_dup+=1
    da=kv.get('deauth_alert')=='1'; ba=kv.get('ble_alert')=='1'; fa=kv.get('flipper_alert')=='1'
    rows=[('WiFi Deauth',2 if da else 0,'%s/5s  %sGHz'%(kv.get('deauth_count','0'),kv.get('deauth_band','-'))),
          ('BLE Spam',2 if ba else 0,'%s spoofed MACs'%kv.get('ble_macs','0')),
          ('Flipper Zero',1 if fa else 0,'%s nearby'%kv.get('flipper_count','0')),
          ('Evil Twin',2 if et_sus else (1 if et_dup else 0),('%d suspect'%et_sus if et_sus else ('%d dup SSID'%et_dup if et_dup else 'none'))),
          ('Scene',-1,'WiFi %d   BLE %s'%(len(aps),kv.get('ble_total','0')))]
    anyalert=da or ba or fa or et_sus
    if anyalert:
        rr(d,(10,34,W-10,72),fill=(120,20,20),outline=(235,80,80),w=2,r=8); ct(d,W//2,53,'!!  THREATS DETECTED  !!',F_NM,(255,190,190))
    else:
        rr(d,(10,34,W-10,72),fill=PANEL,outline=ACC,w=1,r=8); ct(d,W//2,53,'ALL CLEAR  -  watching',F_NM,ACC)
    y=86
    COL={0:(30,200,121),1:(235,180,40),2:(235,80,80)}; LBL={0:'OK',1:'!',2:'ALERT'}
    for name,lvl,metric in rows:
        c=COL.get(lvl,(120,130,150))
        d.ellipse((18,y+5,30,y+17),fill=c)
        lt(d,40,y+4,name,F_NM,FG); lt(d,180,y+6,str(metric)[:30],F_SM,DIM)
        if lvl>=0: ct(d,W-44,y+10,LBL[lvl],F_SM,c)
        y+=34
    lt(d,16,H-28,'all detectors at once  -  %ss  -  passive / alert-only'%kv.get('dur','0'),F_TINY,DIM)
def draw_radar_eviltwin(d):
    topbar(d,'EVIL-TWIN DETECTOR')
    aps=wifi_list or []
    groups={}
    for ap in aps:
        ssid=ap[0]
        if not ssid or ssid=='<hidden>': continue
        groups.setdefault(ssid,[]).append(ap)
    suspects=[]; dups=[]
    for ssid,lst in groups.items():
        bssids={a[5] for a in lst if a[5]}
        if len(bssids)<2: continue
        encs=sorted({(a[3] or '?') for a in lst})
        sec={e for e in encs if ('WPA' in e.upper() or 'WEP' in e.upper())}
        ins={e for e in encs if e not in sec}
        if sec and ins: suspects.append((ssid,len(bssids),encs))
        else: dups.append((ssid,len(bssids),encs))
    if suspects:
        rr(d,(10,34,W-10,74),fill=(120,20,20),outline=(235,80,80),w=2,r=8)
        ct(d,W//2,48,'!!  POSSIBLE EVIL TWIN  !!',F_NM,(255,190,190))
        ct(d,W//2,64,'%d SSID with open + secured clones'%len(suspects),F_SM,(255,215,215))
    elif dups:
        rr(d,(10,34,W-10,74),fill=(120,80,10),outline=(235,180,40),w=2,r=8)
        ct(d,W//2,48,'%d DUPLICATE SSID(s)'%len(dups),F_NM,(255,225,180))
        ct(d,W//2,64,'multiple BSSIDs - could be mesh/extender',F_SM,(255,230,200))
    else:
        rr(d,(10,34,W-10,74),fill=PANEL,outline=ACC,w=1,r=8)
        ct(d,W//2,48,'NO CLONES  -  %d APs seen'%len(aps),F_NM,ACC)
        ct(d,W//2,64,'no SSID broadcast by multiple BSSIDs',F_SM,DIM)
    y=88
    if suspects:
        lt(d,16,y,'evil-twin suspects (open + secured):',F_SM,(235,80,80)); y+=18
        for ssid,n,encs in suspects[:4]:
            lt(d,26,y,str(ssid)[:24],F_NM,FG); lt(d,250,y,('%dx %s'%(n,'/'.join(encs)))[:18],F_SM,(235,150,150)); y+=20
        y+=4
    if dups:
        lt(d,16,y,'duplicate SSIDs (likely mesh):',F_SM,(235,180,40)); y+=18
        for ssid,n,encs in dups[:5]:
            lt(d,26,y,str(ssid)[:24],F_SM,FG); lt(d,250,y,('%dx %s'%(n,'/'.join(encs)))[:18],F_TINY,DIM); y+=18
    if not suspects and not dups:
        lt(d,26,150,('analyzing %d APs...'%len(aps)) if not aps else 'all APs have a unique SSID/BSSID pairing',F_SM,DIM)
    lt(d,16,H-30,'enc-mismatch = real risk; duplicate SSID alone is often legit',F_TINY,DIM)
def radar_flipper_start():
    try: os.remove('/tmp/acid_radar_flipper_stop')
    except Exception: pass
    try: open('/tmp/acid_radar_flipper','w').write('alert=0 count=0 dur=0')
    except Exception: pass
    try: subprocess.Popen(['setsid','python3','/usr/local/bin/acid-flipper-detect.py'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def radar_flipper_stop():
    try: open('/tmp/acid_radar_flipper_stop','w').write('1')
    except Exception: pass
def draw_radar_flipper(d):
    topbar(d,'FLIPPER DETECTOR')
    kv={}; flips=[]
    for i,l in enumerate(_radar_read('/tmp/acid_radar_flipper')):
        if i==0:
            for tok in l.split():
                if '=' in tok: k,v=tok.split('=',1); kv[k]=v
        else:
            p=l.split('|')
            if p[0]=='F' and len(p)>3: flips.append((p[1],p[2],p[3]))
    alert=kv.get('alert')=='1'
    if alert:
        rr(d,(10,34,W-10,74),fill=(120,70,10),outline=(235,150,40),w=2,r=8)
        ct(d,W//2,48,'!!  FLIPPER ZERO DETECTED  !!',F_NM,(255,220,170))
        ct(d,W//2,64,'%s nearby'%kv.get('count','0'),F_SM,(255,225,190))
    else:
        rr(d,(10,34,W-10,74),fill=PANEL,outline=ACC,w=1,r=8)
        ct(d,W//2,48,'MONITORING  -  no Flipper',F_NM,ACC)
        ct(d,W//2,64,'watching BLE for Flipper Zero signature',F_SM,DIM)
    lt(d,16,90,'watching: %ss   match: name "Flipper*" + BLE service'%kv.get('dur','0'),F_SM,DIM)
    d.line([(10,110),(W-10,110)],fill=LINE)
    lt(d,16,118,'detected Flippers:',F_SM,(235,150,40)); y=140
    if flips:
        for name,mac,rssi in flips[:4]:
            try: rv=int(rssi)
            except Exception: rv=-99
            sc=(25,200,121) if rv>-60 else (230,180,40) if rv>-75 else (235,80,80)
            d.ellipse((20,y+3,30,y+13),fill=sc)
            lt(d,38,y,str(name)[:24],F_NM,FG); lt(d,38,y+16,mac,F_TINY,DIM)
            lt(d,W-72,y+6,'%sdBm'%rssi,F_SM,sc); y+=36
    else:
        lt(d,26,y,'none',F_SM,DIM)
    lt(d,16,H-30,'alert-only: detects Flipper BLE presence, no attack',F_TINY,DIM)
DRV2CHIP={'mt76x2u':'MT7612U/ACM','rtl8812au':'RTL8812AU/ACH','rtl8821au':'RTL8821AU/Archer','rtl8xxxu':'RTL8188EUS','r8188eu':'RTL8188EUS','8188eu':'RTL8188EUS','brcmfmac':'onboard BCM','lan78xx':'ethernet'}
ROLETAG={0:'SSH',1:'MON',2:'AP',3:'CLI',4:'IDLE',5:'DOWN'}
def _rsh(c):
    try: return subprocess.run(['bash','-c',c],capture_output=True,timeout=4).stdout.decode('utf-8','replace').strip()
    except Exception: return ''
def ssh_uplink_iface():
    return _rsh("ip route get 1.1.1.1 2>/dev/null | grep -oE 'dev [a-z0-9]+' | head -1 | awk '{print $2}'") or '?'
def wifi_status_scan():
    global radio_rows,ssh_iface,mon_iface
    up=ssh_uplink_iface(); ssh_iface=up; mon='?'; rows=[]
    aroles=(acid_wifiroles.load_roles() if acid_wifiroles else {})
    apresent=(acid_wifiroles.present_adapters() if acid_wifiroles else {})
    for w in _rsh("ls /sys/class/net | grep -E '^wlan'").split():
        drv=_rsh("basename $(readlink /sys/class/net/%s/device/driver 2>/dev/null)"%w)
        chip=DRV2CHIP.get(drv,drv or '?')
        st=_rsh("cat /sys/class/net/%s/operstate 2>/dev/null"%w)
        ftype=_rsh("cat /sys/class/net/%s/type 2>/dev/null"%w)   # 803 = monitor (no iw needed)
        ipa=_rsh("ip -4 addr show %s 2>/dev/null | awk '/inet /{print $2}'"%w)
        ssid=_rsh("iw dev %s link 2>/dev/null | sed -n 's/.*SSID: //p'"%w)
        if w==up: role='SSH uplink'; live='ssh'; pri=0
        elif ftype=='803' or 'mon' in w: role='monitor'; live='mon'; mon=w; pri=1
        elif ssid: role='client: '+ssid; live='cli'; pri=3
        elif st in ('up','dormant'): role='up / free'; live='idle'; pri=4
        else: role='DOWN / free'; live='down'; pri=5
        serves=(acid_wifiroles.serving(w,apresent,aroles) if acid_wifiroles else '')
        pinned=(acid_wifiroles.role_of(drv,aroles) if (acid_wifiroles and drv) else '')
        note=''
        if ('MON' in pinned or 'DUCK' in pinned) and w==up: note='busy: SSH'
        elif 'SSH' in pinned and w!=up: note='boot-pending'
        rows.append({'if':w,'chip':chip,'role':role,'ip':ipa,'pri':pri,'live':live,'assigned':serves,'note':note})
    rows.sort(key=lambda r:r['pri'])
    radio_rows=rows; mon_iface=mon
LIVECOL={'ssh':(235,80,80),'mon':(30,200,121),'ap':(235,130,55),'cli':(70,130,235),'idle':(190,180,90),'down':(120,120,120)}
def draw_wifistatus(d):
    topbar(d,'RADIO STATUS')
    rr(d,(98,4,148,24),outline=ACC,w=1,r=5); ct(d,123,15,'scan',F_SM,ACC)
    if not radio_rows:
        ct(d,W//2,150,'scanning radios...',F_NM,DIM); return
    lt(d,12,36,'%d radios   live SSH = %s   (assign in Settings > WiFi Roles)'%(len(radio_rows),ssh_iface),F_TINY,DIM)
    y=50
    for r in radio_rows:
        rc=LIVECOL.get(r['live'],DIM)
        rr(d,(8,y,472,y+42),fill=TILE,outline=LINE,w=1,r=8)
        d.ellipse((16,y+8,26,y+18),fill=rc)
        lt(d,34,y+13,'%-9s %s'%(r['if'],r['chip']),F_NM,FG)
        if r['assigned']:
            rr(d,(382,y+5,466,y+21),fill=PANEL,outline=(210,140,40),w=1,r=6); ct(d,424,y+13,'assigned '+r['assigned'],F_TINY,(210,140,40))
        else:
            ct(d,424,y+13,'unassigned',F_TINY,DIM)
        lt(d,34,y+30,'live: '+r['role']+(('   '+r['ip']) if r['ip'] else ''),F_TINY,rc)
        if r['note']:
            ct(d,430,y+30,r['note'],F_TINY,(235,80,80) if r['note']=='busy: SSH' else (210,140,40))
        y+=46
    lt(d,12,H-14,'green=recon  red=SSH(never touch)  blue=client  grey=free/down',F_TINY,DIM)
# ---- WiFi Roles: assign which adapter each service uses (tap chip = cycle) ----
ROLE_ROWS=[('ssh','SSH + Internet  (every boot)'),('monitor','Pwnagotchi / Radar / Wardrive'),('badusb','Bad USB (Pico link)')]
roles_edit={}; roles_confirm=None; roles_confirm_t=0.0; roles_status=''; roles_status_t=0.0
def roles_enter():
    global roles_edit,roles_confirm
    roles_edit=(acid_wifiroles.load_roles() if acid_wifiroles else {r:None for r,_ in ROLE_ROWS})
    roles_confirm=None
def roles_cycle(role):
    global roles_edit
    if not acid_wifiroles: return
    present=list(acid_wifiroles.present_adapters().keys())
    order=[None]+[c for c in acid_wifiroles.PRIORITY if c in present]
    cur=roles_edit.get(role)
    nxt=order[(order.index(cur)+1)%len(order)] if cur in order else (order[0] if order else None)
    roles_edit[role]=nxt; acid_wifiroles.save_roles(roles_edit)
def _roles_apply(fn,*a):
    global roles_status,roles_status_t
    roles_status='applying...'; roles_status_t=time.time()
    def run():
        global roles_status,roles_status_t
        try: ok,msg=fn(*a)
        except Exception as e: ok,msg=False,str(e)[:40]
        roles_status=('OK: ' if ok else 'ERR: ')+msg; roles_status_t=time.time()
    threading.Thread(target=run,daemon=True).start()
def draw_wifiroles(d):
    global roles_status
    topbar(d,'WiFi ROLES')
    if not acid_wifiroles:
        ct(d,W//2,150,'acid_wifiroles module missing',F_NM,DIM); return
    present=acid_wifiroles.present_adapters()
    lt(d,12,40,'tap a chip to cycle  -  AUTO = highest-priority adapter present',F_TINY,DIM)
    y0=48
    for i,(role,label) in enumerate(ROLE_ROWS):
        y=y0+i*70
        rr(d,(10,y,470,y+62),fill=TILE,outline=LINE,w=1,r=10)
        lt(d,20,y+15,label,F_SM,FG)
        chip=roles_edit.get(role); chip_txt=acid_wifiroles.CHIP_LABEL.get(chip,'AUTO') if chip else 'AUTO'
        rr(d,(20,y+26,270,y+52),fill=PANEL,outline=ACC,w=1,r=8); ct(d,145,y+39,chip_txt,F_SM,ACC)
        iface,rchip=acid_wifiroles.resolve(role,roles=roles_edit,present=present)
        live_ok=iface is not None
        d.ellipse((280,y+34,290,y+44),fill=(30,200,121) if live_ok else (200,70,70))
        lt(d,296,y+39,('live: %s'%iface) if live_ok else 'no adapter free',F_TINY,DIM if live_ok else (200,90,90))
        if role=='ssh':
            rr(d,(376,y+26,419,y+52),fill=(30,90,60),outline=ACC,w=1,r=7); ct(d,397,y+39,'START',F_TINY,FG)
            armed=(roles_confirm=='ssh_stop' and time.time()-roles_confirm_t<4)
            rr(d,(423,y+26,466,y+52),fill=(210,140,40) if armed else (90,45,45),outline=(200,90,90),w=1,r=7)
            ct(d,444,y+39,'sure?' if armed else 'STOP',F_TINY,BG if armed else (255,210,210))
        elif role=='monitor':
            armed=(roles_confirm=='monitor' and time.time()-roles_confirm_t<4)
            rr(d,(376,y+26,466,y+52),fill=(210,140,40) if armed else TILE,outline=ACC,w=1,r=8)
            ct(d,421,y+39,'tap again' if armed else 'SET',F_TINY if armed else F_SM,BG if armed else ACC)
    ct(d,240,H-16,roles_status[:58] if (roles_status and time.time()-roles_status_t<6) else \
       'chip=cycle adapter  ·  SSH START/STOP live  ·  Monitor SET (restarts pwn)',F_TINY,DIM)
def touch_wifiroles(tx,ty):
    global roles_confirm,roles_confirm_t,roles_status,roles_status_t
    y0=48
    for i,(role,_label) in enumerate(ROLE_ROWS):
        y=y0+i*70
        if not (y+26<=ty<=y+52): continue
        if 20<=tx<=270:
            roles_cycle(role); roles_confirm=None; return
        if role=='ssh':
            if 376<=tx<=419:                       # START (connect SSH via priority)
                roles_confirm=None; _roles_apply(acid_wifiroles.apply_ssh_start); return
            if 423<=tx<=466:                       # STOP (confirm-gated - drops SSH)
                now=time.time()
                if roles_confirm=='ssh_stop' and now-roles_confirm_t<4:
                    roles_confirm=None; _roles_apply(acid_wifiroles.apply_ssh_stop)
                else:
                    roles_confirm='ssh_stop'; roles_confirm_t=now
                return
        elif role=='monitor' and 376<=tx<=466:     # SET (apply monitor live, confirm-gated)
            now=time.time()
            if roles_confirm=='monitor' and now-roles_confirm_t<4:
                roles_confirm=None
                chip=roles_edit.get('monitor') or (acid_wifiroles.resolve('monitor',roles=roles_edit)[1] if acid_wifiroles else None)
                if not chip: roles_status='pick a chip first'; roles_status_t=now; return
                _roles_apply(acid_wifiroles.apply_monitor,chip)
            else:
                roles_confirm='monitor'; roles_confirm_t=now
            return
def draw_settings(d):
    topbar(d,'SETTINGS')
    lt(d,22,44,'THEME  -  tap anywhere in this box',F_SM,DIM)
    rr(d,(14,56,466,150),fill=PANEL,outline=LINE,w=1,r=12); lt(d,34,103,'Appearance',F_NM,FG)
    px1,py1,px2,py2=270,84,452,122; pm=(py1+py2)//2
    rr(d,(px1,py1,px2,py2),fill=TILE,outline=LINE,w=1,r=19)
    if theme=='dark':
        rr(d,(px1+4,py1+4,px1+90,py2-4),fill=ACC,r=15); ct(d,px1+47,pm,'dark',F_SM,BG); ct(d,px2-45,pm,'light',F_SM,DIM)
    else:
        rr(d,(px2-90,py1+4,px2-4,py2-4),fill=ACC,r=15); ct(d,px1+47,pm,'dark',F_SM,DIM); ct(d,px2-45,pm,'light',F_SM,BG)
    ct(d,240,138,'now: %s'%theme,F_SM,DIM)
    d.line([(10,168),(W-10,168)],fill=LINE)
    rr(d,(14,180,234,224),fill=TILE,outline=ACC,w=2,r=12); ct(d,124,202,'calibrate touch',F_NM,ACC)
    rr(d,(246,180,466,224),fill=TILE,outline=(70,130,235),w=2,r=12); ct(d,356,202,'System & Power',F_NM,(70,130,235))
    rr(d,(14,232,234,274),fill=TILE,outline=(30,200,121),w=2,r=12); ct(d,124,253,'Radio Status',F_NM,(30,200,121))
    rr(d,(246,232,466,274),fill=TILE,outline=(210,140,40),w=2,r=12); ct(d,356,253,'WiFi Roles',F_NM,(210,140,40))
    ct(d,240,288,'which adapter is SSH / monitor / AP  -  and who uses which',F_TINY,DIM)
SVC=[('Pwnagotchi','pwnagotchi'),('Bluetooth','bluetooth'),('HS-Clean','acid-hs-clean.timer'),('HDMI Mirror','acid-hdmi-mirror'),('Screen Stream','acid-fb-stream')]
SVC_YY=[36,66,96,126,156]   # row tops; draw_system() and the System touch handler share this
svc_state={}
def svc_refresh():
    for nm,u in SVC:
        try: svc_state[u]=(subprocess.run(['systemctl','is-active',u],capture_output=True,timeout=2).stdout.decode().strip() or 'inactive')
        except Exception: svc_state[u]='?'
def svc_toggle(u):
    act='stop' if svc_state.get(u)=='active' else 'start'
    try: subprocess.Popen(['setsid','systemctl',act,u],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
    svc_state[u]='...'
def hdmi_toggle():
    # HDMI is a swap, not a single-unit toggle: ON = mirror the UI (console hidden),
    # OFF = plain console back on HDMI (the default). Mirrors the hdmistart/hdmimirror aliases.
    on=svc_state.get('acid-hdmi-mirror')=='active'
    try:
        if on:
            subprocess.Popen(['setsid','systemctl','stop','acid-hdmi-mirror'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
            subprocess.Popen(['setsid','systemctl','start','getty@tty1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
        else:
            subprocess.Popen(['setsid','systemctl','stop','getty@tty1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
            subprocess.Popen(['setsid','systemctl','start','acid-hdmi-mirror'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
    svc_state['acid-hdmi-mirror']='...'
def restart_os():
    try: subprocess.Popen(['setsid','systemctl','restart','acidzero'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def power_cmd(c):
    try: subprocess.Popen(['setsid','systemctl',c],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def draw_system(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'SYSTEM & POWER',F_TIT,FG)
    for i,(nm,u) in enumerate(SVC):
        y=SVC_YY[i]; st=svc_state.get(u,'?'); on=(st=='active')
        rr(d,(10,y,470,y+28),fill=TILE,outline=LINE,w=1,r=7)
        dot=(25,200,121) if on else (235,180,40) if st in ('...','activating','?') else (235,80,80)
        d.ellipse((20,y+9,30,y+19),fill=dot); lt(d,40,y+14,nm,F_NM,FG); lt(d,300,y+14,st,F_SM,DIM)
        rr(d,(384,y+4,462,y+24),fill=((235,80,80) if on else (25,160,90)),r=5); ct(d,423,y+14,('STOP' if on else 'START'),F_SM,(245,245,245))
    rr(d,(10,192,470,222),fill=(30,120,210),r=8); ct(d,W//2,207,'RESTART ACID ZERO',F_NM,(240,248,255))
    if sys_confirm=='reboot' and time.time()-sys_confirm_t<5: rr(d,(10,228,470,258),fill=(235,140,40),r=8); ct(d,W//2,243,'tap again to REBOOT',F_NM,(25,12,0))
    else: rr(d,(10,228,470,258),outline=(235,140,40),w=2,r=8); ct(d,W//2,243,'REBOOT SYSTEM',F_NM,(235,140,40))
    if sys_confirm=='shutdown' and time.time()-sys_confirm_t<5: rr(d,(10,264,470,294),fill=(220,60,60),r=8); ct(d,W//2,279,'tap again to SHUTDOWN',F_NM,(255,235,235))
    else: rr(d,(10,264,470,294),outline=(220,60,60),w=2,r=8); ct(d,W//2,279,'SHUTDOWN',F_NM,(220,60,60))
def draw_calibrate(d,step):
    ct(d,W//2,52,'TOUCH  CALIBRATION',F_TIT,ACC); ct(d,W//2,82,'tap each green target   (%d / 4)'%(min(step+1,4)),F_NM,FG)
    ct(d,W//2,150,'use stylus / nail, tap firmly on the +',F_SM,DIM); ct(d,W//2,175,'order: TL  ->  TR  ->  BR  ->  BL',F_SM,DIM)
    if step<4:
        tx,ty=CAL_TARGETS[step]
        d.ellipse((tx-17,ty-17,tx+17,ty+17),outline=ACC,width=2); d.line((tx-24,ty,tx+24,ty),fill=ACC,width=2); d.line((tx,ty-24,tx,ty+24),fill=ACC,width=2); d.ellipse((tx-3,ty-3,tx+3,ty+3),fill=ACC)
def draw_wifi(d):
    view=wifi_view(); n=len(view); k=len(wifi_sel)
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'WIFI HUNTER',F_TIT,FG); learn_btn(d)
    if wifi_list is None: ct(d,W//2,160,'reading monitor...',F_NM,DIM); return
    s='%dAP %dsel'%(n,k); bb=d.textbbox((0,0),s,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),15,s,F_SM,ACC)
    rr(d,(8,31,234,49),outline=LINE,w=1,r=5); lt(d,18,40,'sort: '+wifi_sort,F_SM,ACC)
    rr(d,(246,31,472,49),outline=LINE,w=1,r=5); lt(d,256,40,'filter: '+wifi_filter,F_SM,(70,130,235))
    if n==0: ct(d,W//2,150,'no APs (filter '+wifi_filter+')',F_SM,DIM)
    y=52; per=6
    for ap in view[wifi_off:wifi_off+per]:
        essid,ch,rssi,enc,cl,mac,clients=ap; seld=mac in wifi_sel
        if seld: d.rectangle((0,y,3,y+29),fill=ACC)
        rr(d,(9,y+8,23,y+22),outline=(ACC if seld else DIM),w=1,r=3)
        if seld: rr(d,(12,y+11,20,y+19),fill=ACC,r=2)
        sc=(25,200,121) if rssi>-60 else (230,180,40) if rssi>-72 else (235,130,55) if rssi>-83 else (235,80,80)
        d.ellipse((31,y+10,41,y+20),fill=sc); lt(d,49,y+15,essid[:18],F_NM,FG)
        info=('%dcl '%cl if cl else '')+'ch%s %s %ddBm'%(ch,enc[:5],rssi)
        bb=d.textbbox((0,0),info,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),y+15,info,F_SM,DIM)
        d.line([(8,y+29),(W-8,y+29)],fill=LINE); y+=30
    pages=max(1,(n+per-1)//per); pg=wifi_off//per+1
    rr(d,(10,234,118,256),outline=ACC,w=1,r=5); ct(d,64,245,'UP',F_SM,ACC)
    ct(d,W//2,245,'page %d/%d'%(pg,pages),F_SM,DIM)
    rr(d,(W-118,234,W-10,256),outline=ACC,w=1,r=5); ct(d,W-64,245,'DOWN',F_SM,ACC)
    rr(d,(8,260,88,296),outline=ACC,w=1,r=6); ct(d,48,278,'ALL',F_SM,ACC)
    rr(d,(94,260,172,296),outline=DIM,w=1,r=6); ct(d,133,278,'CLR',F_SM,DIM)
    if deauth_run:
        rr(d,(178,260,330,296),fill=(235,80,80),r=6); ct(d,254,278,'STOP %d'%len(deauth_macs),F_NM,(245,245,245))
    else:
        rr(d,(178,260,330,296),outline=(235,80,80),w=2,r=6); ct(d,254,278,'DEAUTH %d'%k,F_NM,(235,80,80))
    rr(d,(336,260,472,296),outline=(70,130,235),w=1,r=6); ct(d,404,278,'CONNECT',F_SM,(70,130,235))
    if wifi_status and time.time()-wifi_status_t<5:
        rr(d,(50,100,430,140),fill=PANEL,outline=ACC,w=1,r=8); ct(d,W//2,120,wifi_status,F_NM,ACC)
    if wifi_confirm:
        rr(d,(60,90,420,180),fill=PANEL,outline=ACC,w=2,r=10)
        msg=('Deauth %d AP (live)?'%k if wifi_confirm=='deauth' else 'Connect: %s ?'%wifi_confirm_ssid[:16])
        ct(d,W//2,116,msg,F_NM,FG)
        rr(d,(80,146,230,174),fill=((235,80,80) if wifi_confirm=='deauth' else (70,130,235)),r=6); ct(d,155,160,'YES',F_NM,(245,245,245))
        rr(d,(250,146,400,174),outline=DIM,w=1,r=6); ct(d,325,160,'NO',F_NM,DIM)
def draw_wifi_clients(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'CLIENTS',F_TIT,FG)
    if not wifi_focus: ct(d,W//2,160,'no AP',F_NM,DIM); return
    essid,ch,rssi,enc,cl,mac,clients=wifi_focus
    lt(d,12,44,essid[:22],F_NM,ACC); lt(d,12,64,'%s  ch%s %s'%(mac,ch,enc),F_SM,DIM)
    d.line([(8,78),(W-8,78)],fill=LINE)
    if not clients: ct(d,W//2,150,'no clients connected',F_SM,DIM)
    else:
        y=84
        for c in clients[:6]:
            cm,cv,cr=c
            sc=(25,200,121) if cr>-65 else (230,180,40) if cr>-78 else (235,80,80)
            d.ellipse((12,y+6,22,y+16),fill=sc); lt(d,30,y+11,cm,F_NM,FG)
            info='%s %ddBm'%(cv[:12],cr); bb=d.textbbox((0,0),info,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),y+11,info,F_SM,DIM)
            d.line([(8,y+24),(W-8,y+24)],fill=LINE); y+=26
    ct(d,W//2,248,'tap a client to deauth it',F_SM,DIM)
    rr(d,(120,260,360,296),outline=(235,80,80),w=2,r=6); ct(d,240,278,'DEAUTH THIS AP',F_NM,(235,80,80))
    if wifi_status and time.time()-wifi_status_t<4:
        rr(d,(60,200,420,234),fill=PANEL,outline=ACC,w=1,r=8); ct(d,W//2,217,wifi_status,F_SM,ACC)
def draw_wifikey(d):
    issid=(kb_target=='epssid')
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,('SET SSID' if issid else 'CONNECT WIFI'),F_TIT,FG)
    lt(d,12,40,('Evil Portal AP name' if issid else 'SSID: '+wifi_confirm_ssid[:26]),F_SM,DIM)
    rr(d,(10,48,470,76),fill=TILE,outline=ACC,w=1,r=6); lt(d,18,62,(kb_pw or ('tap keys to type SSID' if issid else 'tap keys to type password'))[:42],F_NM,(FG if kb_pw else DIM))
    for ch,x1,y1,x2,y2,kind in kb_keys():
        cx=(x1+x2)//2; cy=(y1+y2)//2
        if kind=='go': rr(d,(x1,y1,x2,y2),fill=ACC,r=6); ct(d,cx,cy,'GO',F_NM,BG)
        elif kind=='cancel': rr(d,(x1,y1,x2,y2),fill=(235,80,80),r=6); ct(d,cx,cy,'esc',F_SM,(245,245,245))
        elif kind=='shift': rr(d,(x1,y1,x2,y2),fill=(ACC if kb_shift else TILE),outline=LINE,w=1,r=6); ct(d,cx,cy,'shft',F_SM,(BG if kb_shift else DIM))
        elif kind=='sym': rr(d,(x1,y1,x2,y2),fill=(ACC if kb_sym else TILE),outline=LINE,w=1,r=6); ct(d,cx,cy,ch,F_SM,(BG if kb_sym else DIM))
        elif kind=='c': rr(d,(x1,y1,x2,y2),fill=TILE,outline=LINE,w=1,r=6); ct(d,cx,cy,ch,F_NM,FG)
        else: rr(d,(x1,y1,x2,y2),fill=TILE,outline=LINE,w=1,r=6); ct(d,cx,cy,ch,F_SM,DIM)
def draw_soon(d,name,k,col):
    topbar(d,name.upper()); ic(d,k,W//2,138,col); ct(d,W//2,188,'coming soon',F_BIG,DIM); ct(d,W//2,214,'tap  < back  to return',F_SM,DIM)
def draw_evil(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'EVIL PORTAL',F_TIT,FG); learn_btn(d)
    run=ep_running()
    def cfg(y0,y1,key,val,vc=None):
        rr(d,(8,y0,472,y1),fill=TILE,outline=LINE,w=1,r=7); lt(d,18,(y0+y1)//2,key,F_SM,DIM)
        s=str(val); bb=d.textbbox((0,0),s,font=F_NM); lt(d,W-18-(bb[2]-bb[0]),(y0+y1)//2,s,F_NM,vc or FG)
    cfg(44,68,'SSID  (tap to edit)',ep_ssid[:20],ACC)
    cfg(70,94,'Portal page  (tap)',ep_tpl,(70,130,235))
    rr(d,(8,96,234,120),fill=TILE,outline=LINE,w=1,r=7); lt(d,18,108,'Channel',F_SM,DIM); ct(d,212,108,str(ep_ch),F_NM,ACC)
    rr(d,(246,96,472,120),fill=TILE,outline=LINE,w=1,r=7); lt(d,256,108,'Attempts',F_SM,DIM); ct(d,450,108,str(ep_att),F_NM,ACC)
    rr(d,(8,122,472,146),fill=TILE,outline=LINE,w=1,r=7); lt(d,18,134,'Internet after login',F_SM,DIM)
    ct(d,450,134,('ON' if ep_pass else 'OFF'),F_NM,((25,200,121) if ep_pass else DIM))
    if run: rr(d,(8,150,472,186),fill=(225,70,70),r=8); ct(d,W//2,168,'STOP  PORTAL',F_BIG,(250,250,250))
    else: rr(d,(8,150,472,186),fill=(23,150,86),r=8); ct(d,W//2,168,'START  PORTAL',F_BIG,(4,20,12))
    if run: st='LIVE on %s  -  %d client(s)'%(ep_apif(),ep_nclients()); sc=(25,200,121)
    else: st=(ep_status or 'stopped - tap START'); sc=DIM
    ct(d,W//2,197,st,F_SM,sc)
    d.line([(8,208),(W-8,208)],fill=LINE)
    lt(d,12,219,'CAPTURED  (%d)'%ep_ncreds(),F_SM,(235,180,40))
    cr=ep_creds(4)
    if not cr: ct(d,W//2,262,'no credentials captured yet',F_SM,DIM)
    else:
        y=234
        for l in cr:
            parts=l.split(' | '); tm=parts[0] if parts else ''; cd=(parts[-1] if parts else l)
            lt(d,12,y,tm,F_TINY,DIM); lt(d,76,y,cd[:42],F_SM,FG); y+=16
def draw_handshake(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'HANDSHAKE HUNTER',F_TIT,FG); learn_btn(d)
    cap=hs_captured(); tot=hs_count()
    s='%d saved'%tot; bb=d.textbbox((0,0),s,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),15,s,F_SM,ACC)
    lt(d,12,40,'tap an AP to HUNT (deauth+capture ~30s):',F_SM,DIM)
    view=wifi_view() if wifi_list else []
    if wifi_list is None: ct(d,W//2,150,'reading monitor...',F_NM,DIM); return
    if not view: ct(d,W//2,128,'no APs in range yet',F_SM,DIM)
    y=52; per=5
    for ap in view[hs_off:hs_off+per]:
        essid,ch,rssi,enc,cl,mac,clients=ap
        got=mac.replace(':','').lower() in cap
        sc=(25,200,121) if rssi>-65 else (230,180,40) if rssi>-78 else (235,80,80)
        d.ellipse((14,y+9,24,y+19),fill=sc); lt(d,32,y+14,essid[:15],F_NM,FG)
        if got: rr(d,(W-158,y+5,W-104,y+23),fill=(25,150,86),r=4); ct(d,W-131,y+14,'GOT',F_SM,(4,20,12))
        lt(d,W-96,y+14,'ch%s %dcl'%(ch,cl),F_TINY,DIM)
        d.line([(8,y+28),(W-8,y+28)],fill=LINE); y+=30
    n=len(view); pages=max(1,(n+per-1)//per); pg=hs_off//per+1
    rr(d,(10,210,118,232),outline=ACC,w=1,r=5); ct(d,64,221,'UP',F_SM,ACC)
    ct(d,W//2,221,'page %d/%d  -  %d AP'%(pg,pages,n),F_SM,DIM)
    rr(d,(W-118,210,W-10,232),outline=ACC,w=1,r=5); ct(d,W-64,221,'DOWN',F_SM,ACC)
    rr(d,(10,238,235,270),outline=(235,180,40),w=2,r=6); ct(d,122,254,'CONVERT ALL .22000',F_SM,(235,180,40))
    rr(d,(245,238,470,270),outline=(70,130,235),w=1,r=6); ct(d,357,254,'how to crack',F_SM,(70,130,235))
    r=hs_result()
    if r.startswith('GOT'): rr(d,(8,276,472,300),fill=(20,90,50),r=6); ct(d,W//2,288,r[:52],F_SM,(180,255,210))
    elif r.startswith('no capture') or r.startswith('FAIL'): rr(d,(8,276,472,300),fill=(90,30,30),r=6); ct(d,W//2,288,r[:52],F_SM,(255,180,180))
    elif r and ('capturing' in r or r=='starting'): ct(d,W//2,288,'hunting... '+r[:38],F_SM,ACC)
    elif hs_status and time.time()-hs_status_t<30: ct(d,W//2,288,hs_status[:52],F_SM,ACC)
BLE_PER_PAGE=6
def draw_ble_scan(d):
    global ble_page
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'BLE SCAN',F_TIT,FG); learn_btn(d)
    scanning=ble_scanning(); cnt=ble_dev_count()
    total=max(1,(cnt+BLE_PER_PAGE-1)//BLE_PER_PAGE); ble_page=min(max(ble_page,0),total-1)
    start=ble_page*BLE_PER_PAGE; devs=ble_devices(BLE_PER_PAGE,start)
    s=('scanning...' if scanning else '%d found'%cnt); bb=d.textbbox((0,0),s,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),15,s,F_SM,ACC)
    rr(d,(10,34,150,62),fill=(30,120,210),r=7); ct(d,80,48,'SCAN',F_NM,(240,248,255))
    lt(d,165,48,'nearby Bluetooth LE',F_SM,DIM)
    if not devs:
        ct(d,W//2,160,('scanning ~8s...' if scanning else 'tap SCAN to find BLE devices'),F_SM,DIM); return
    y=70
    for mac,rssi,atype,lbl in devs:
        rv=int(rssi) if rssi.lstrip('-').isdigit() else -99
        sc=(25,200,121) if rv>-60 else (230,180,40) if rv>-75 else (235,130,55) if rv>-88 else (235,80,80)
        d.ellipse((14,y+8,24,y+18),fill=sc)
        lt(d,32,y+11,(lbl or mac)[:30],F_NM,FG)
        lt(d,32,y+23,mac+'  '+atype,F_TINY,DIM)
        info='%sdBm'%rssi; bb=d.textbbox((0,0),info,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),y+15,info,F_SM,(sc))
        d.line([(8,y+31),(W-8,y+31)],fill=LINE); y+=32
    if cnt>BLE_PER_PAGE:
        by=H-24
        rr(d,(10,by,120,by+21),fill=TILE,outline=LINE,w=1,r=6); ct(d,65,by+10,'< PREV',F_SM,FG if ble_page>0 else DIM)
        ct(d,240,by+10,'%d / %d'%(ble_page+1,total),F_SM,FG)
        rr(d,(360,by,470,by+21),fill=TILE,outline=LINE,w=1,r=6); ct(d,415,by+10,'NEXT >',F_SM,FG if ble_page<total-1 else DIM)
def ble_inspect_start(mac):
    try: open('/tmp/acid_ble_inspect_status','w').write('connecting')
    except Exception: pass
    try: open('/tmp/acid_ble_inspect','w').write('')
    except Exception: pass
    try: subprocess.Popen(['setsid','python3','/usr/local/bin/acid-ble-inspect.py',mac],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    except Exception: pass
def ble_insp_status():
    try: return open('/tmp/acid_ble_inspect_status').read().strip()
    except Exception: return ''
def ble_insp_data():
    try: return [l for l in open('/tmp/acid_ble_inspect').read().split('\n') if l]
    except Exception: return []
def draw_ble_inspect(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'BLE INSPECT',F_TIT,FG); learn_btn(d)
    dev=ble_insp_mac; name=''; rows=[]; err=''
    for l in ble_insp_data():
        p=l.split('|')
        if p[0]=='DEV': dev=p[1] if len(p)>1 else dev; name=p[2] if len(p)>2 else ''
        elif p[0]=='ERR': err=p[1] if len(p)>1 else 'error'
        elif p[0] in ('S','C','D'): rows.append((p[0],p[1] if len(p)>1 else '',p[2] if len(p)>2 else '',p[3] if len(p)>3 else ''))
    stt=ble_insp_status(); busy=stt in ('connecting','enumerating')
    lt(d,12,36,(name or dev or '-')[:32],F_NM,ACC); lt(d,12,52,dev,F_TINY,DIM)
    s=stt[:18]; bb=d.textbbox((0,0),s,font=F_SM); lt(d,W-12-(bb[2]-bb[0]),40,s,F_SM,(235,180,40) if busy else DIM)
    if err:
        ct(d,W//2,150,'connect failed',F_NM,(235,80,80)); ct(d,W//2,174,err[:48],F_SM,DIM); return
    if not rows:
        ct(d,W//2,160,('connecting + reading GATT...' if busy else 'no data'),F_SM,DIM); return
    vis=rows[insp_off:insp_off+9]; y=68
    for kind,short,friendly,val in vis:
        if kind=='S':
            d.rectangle((8,y,W-8,y+22),fill=PANEL); lt(d,14,y+5,('SVC  '+(friendly or short or '?'))[:40],F_SM,ACC); y+=24
        else:
            lt(d,28,y+4,(friendly or short or '?')[:30],F_SM,FG)
            if val:
                vb=d.textbbox((0,0),val[:18],font=F_SM); lt(d,W-12-(vb[2]-vb[0]),y+4,val[:18],F_SM,(30,200,121))
            elif short:
                lt(d,W-58,y+4,'0x'+short,F_TINY,DIM)
            y+=22
    if len(rows)>9:
        ct(d,W//2,H-32,'%d-%d / %d'%(insp_off+1,min(insp_off+9,len(rows)),len(rows)),F_TINY,DIM)
        rr(d,(10,H-48,90,H-26),outline=ACC,w=1,r=6); ct(d,50,H-37,'UP',F_SM,ACC)
        rr(d,(W-90,H-48,W-10,H-26),outline=ACC,w=1,r=6); ct(d,W-50,H-37,'DOWN',F_SM,ACC)
def draw_ble_spam(d):
    d.rectangle((0,0,W,28),fill=BARBG); d.line([(0,28),(W,28)],fill=LINE)
    rr(d,(6,4,92,24),outline=ACC,w=1,r=5); ct(d,49,15,'< back',F_SM,ACC); ct(d,W//2,15,'BLE SPAM',F_TIT,FG); learn_btn(d)
    run=ble_spam_running()
    rr(d,(10,38,470,72),fill=TILE,outline=LINE,w=1,r=8); lt(d,20,55,'Spam mode  (tap to change)',F_SM,DIM); ct(d,412,55,ble_mode.upper(),F_NM,(30,200,230))
    ic(d,'bt',W//2,98,(30,200,230))
    ct(d,W//2,128,BLE_DESC.get(ble_mode,''),F_SM,DIM)
    if run: rr(d,(40,146,440,190),fill=(225,70,70),r=10); ct(d,W//2,168,'STOP SPAM',F_BIG,(250,250,250))
    else: rr(d,(40,146,440,190),fill=(30,150,210),r=10); ct(d,W//2,168,'START SPAM',F_BIG,(240,248,255))
    ct(d,W//2,206,(('LIVE - sent %s  (back = stop)'%ble_spam_sent()) if run else 'stopped'),F_SM,((25,200,121) if run else DIM))
    if run:
        lt(d,14,224,'live log:',F_SM,DIM)
        try: lines=[l for l in open('/tmp/acid_ble_spam_log').read().split('\n') if l.strip()][-3:]
        except Exception: lines=[]
        y=240
        for l in lines: lt(d,18,y,l[:48],F_TINY,ACC); y+=14
    else:
        ct(d,W//2,232,'[!] broadcasts to ALL nearby phones',F_SM,(235,180,40))
        ct(d,W//2,250,'lab / educational only',F_TINY,DIM)
        ct(d,W//2,266,'Pi BT range short (ESP32-C6 = stronger)',F_TINY,DIM)
class Ctx:
    W=W; H=H; FB=FB
    F_TIT=F_TIT; F_NM=F_NM; F_SM=F_SM; F_TILE=F_TILE; F_BIG=F_BIG; F_XL=F_XL; F_TINY=F_TINY
    rr=staticmethod(rr); lt=staticmethod(lt); ct=staticmethod(ct); icon=staticmethod(ic); icon_scaled=staticmethod(ic_scaled); topbar=staticmethod(topbar)
    def __getattr__(self,k):
        g=globals()
        if k in g: return g[k]
        raise AttributeError(k)
    def popen(self,argv): return subprocess.Popen(['setsid']+list(argv),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL)
    def run(self,argv,timeout=20):
        try: return subprocess.run(argv,timeout=timeout,capture_output=True)
        except Exception: return None
    def fread(self,p):
        try: return open(p).read()
        except Exception: return ''
    def fwrite(self,p,data):
        try: open(p,'w').write(data); return True
        except Exception: return False
    def set_screen(self,s):
        global screen; screen=s
    def back(self):
        global screen; screen='home'
    def mark_dirty(self):
        global dirty; dirty=True
    def debounce(self,sec=0.3):
        global _last_act
        if time.time()-_last_act>sec: _last_act=time.time(); return True
        return False
    @property
    def now(self): return time.time()
CTX=Ctx()
def load_plugins():
    import importlib.util as _ilu
    out={}
    try: files=sorted(glob.glob('/usr/local/lib/acid-apps/*.py'))
    except Exception: files=[]
    for f in files:
        try:
            spec=_ilu.spec_from_file_location('acidapp_'+os.path.basename(f)[:-3],f)
            m=_ilu.module_from_spec(spec); spec.loader.exec_module(m)
            meta=getattr(m,'META',None)
            if meta and meta.get('name') and hasattr(m,'draw'): out[meta['name']]=m
        except Exception as e:
            try: open('/tmp/acid_plugin_err.log','a').write('%s: %s\n'%(os.path.basename(f),e))
            except Exception: pass
    return out
PLUGINS=load_plugins()
def load_native():
    out={}
    try: mans=sorted(glob.glob('/usr/local/lib/acid-apps/*/app.json'))
    except Exception: mans=[]
    for mf in mans:
        try:
            meta=json.load(open(mf))
            if meta.get('type')=='native' and meta.get('name') and meta.get('exec'):
                ex=meta['exec']; dd=os.path.dirname(mf)
                if not ex.startswith('/'): ex=os.path.join(dd,ex)
                out[meta['name']]={'exec':ex,'dir':dd,'icon':meta.get('icon','usb'),'color':tuple(meta.get('color',[140,155,180]))}
        except Exception as e:
            try: open('/tmp/acid_plugin_err.log','a').write('native %s: %s\n'%(mf,e))
            except Exception: pass
    return out
NATIVE=load_native()
def build_app_list():
    g=list(APPS); names=set(a[0] for a in g)
    for nm,mm in PLUGINS.items():
        if nm not in names: g.append((nm,mm.META.get('icon','info'),tuple(mm.META.get('color',[140,155,180])))); names.add(nm)
    for nm,info in NATIVE.items():
        if nm not in names: g.append((nm,info['icon'],info['color'])); names.add(nm)
    return g
GRID=build_app_list()
PER=COLS*ROWS
PAGES=max(1,(len(GRID)+PER-1)//PER)
home_page=0
def run_native(name):
    global last_h
    info=NATIVE.get(name)
    if not info: return
    try: subprocess.run([info['exec']],cwd=info['dir'])
    except Exception as e:
        try: open('/tmp/acid_plugin_err.log','a').write('run %s: %s\n'%(name,e))
        except Exception: pass
    last_h=time.time()
screen='home'; cnt=0; last_h=0.0; mi=0; _showtap=[-1,-1,0.0]; cal_raws=[]; _last_act=0.0; cal_msg=''; cal_msg_t=0.0; cur_ip='-'; net_state=False; wifi_list=None; wifi_off=0; wifi_t=0.0; wifi_sel=set(); wifi_status=''; wifi_status_t=0.0; wifi_confirm=None; wifi_confirm_ssid=''; wifi_sort='signal'; wifi_filter='all'; deauth_run=False; deauth_macs=set(); deauth_chans={}; wifi_focus=None; kb_pw=''; kb_shift=False; kb_sym=False; kb_target='wifipw'
ep_ssid='Free WiFi'; ep_tpl='wifi'; ep_ch=6; ep_att=1; ep_pass=False; ep_run=False; ep_status=''; ep_status_t=0.0
hs_off=0; hs_status=''; hs_status_t=0.0; hs_run=False
ble_status=''; ble_status_t=0.0; ble_spam_run=False; ble_mode='sink'
ble_insp_mac=''; insp_off=0; ble_page=0; learn_off=0
radar_sweep=0.0; radar_ble_t=0.0; radar_img=None; radar_img_t=0.0; radar_img_theme=None
ssh_iface='?'; mon_iface='?'; active_radio=''; radio_rows=[]
svc_t=0.0; sys_confirm=''; sys_confirm_t=0.0
if not os.path.exists(CONSENT_FLAG): screen='consent'   # first-run authorization gate
cpu()
last_draw=0.0; REFRESH=1.0; TICK=0.033
threading.Thread(target=face_thread,daemon=True).start()
threading.Thread(target=net_bg_thread,daemon=True).start()
threading.Thread(target=wifi_bg_thread,daemon=True).start()
threading.Thread(target=pwn_bg_thread,daemon=True).start()
while True:
    try:
        try:
            if os.path.exists('/tmp/acid_screen'):
                _v=open('/tmp/acid_screen').read().strip(); os.remove('/tmp/acid_screen')
                if _v.startswith('learn:') and _v.split(':',1)[1] in LEARN: learn_topic=_v.split(':',1)[1]; learn_off=0; screen='learn'
                else: screen=_v
                if screen=='calibrate': cal_raws=[]
                elif screen=='HWInfo': hwinfo_collect()
                elif screen=='WiFiStatus': radio_rows=[]; wifi_status_scan()
                dirty=True
        except Exception: pass
        try:
            if os.path.exists('/tmp/acid_theme'):
                nt=open('/tmp/acid_theme').read().strip(); os.remove('/tmp/acid_theme')
                if nt in THEMES: theme=nt; apply_theme(theme); dirty=True
        except Exception: pass
        now=time.time()
        if _tap['t']>last_h:
            last_h=_tap['t']; tx,ty=_tap['x'],_tap['y']; _showtap[0]=tx; _showtap[1]=ty; _showtap[2]=now; dirty=True
            if screen=='calibrate':
                cal_raws.append((_tap['rx'],_tap['ry']))
                if len(cal_raws)>=4:
                    try:
                        A=np.array([[float(r[0]),float(r[1]),1.0] for r in cal_raws])
                        txs=np.array([float(t[0]) for t in CAL_TARGETS]); tys=np.array([float(t[1]) for t in CAL_TARGETS])
                        cx_=np.linalg.lstsq(A,txs,rcond=None)[0]; cy_=np.linalg.lstsq(A,tys,rcond=None)[0]
                        px=A.dot(cx_); py=A.dot(cy_); res=float(np.max(((px-txs)**2+(py-tys)**2)**0.5))
                        if res<=45:
                            CAL[0],CAL[1],CAL[2]=float(cx_[0]),float(cx_[1]),float(cx_[2]); CAL[3],CAL[4],CAL[5]=float(cy_[0]),float(cy_[1]),float(cy_[2]); save_cal(); cal_msg='calib OK  err %dpx'%int(res)
                        else: cal_msg='calib REJECTED  err %dpx - retry'%int(res)
                    except Exception: cal_msg='calib error'
                    cal_msg_t=now; cal_raws=[]; screen='Settings'
            elif screen=='consent':
                if 258<=ty<=296 and 90<=tx<=390 and now-_last_act>0.3:
                    _last_act=now
                    try: open(CONSENT_FLAG,'w').write('accepted')
                    except Exception: pass
                    screen='home'
            elif screen=='home':
                if ty>=H-20 and PAGES>1 and now-_last_act>0.3:
                    if 175<=tx<=228 and home_page>0: _last_act=now; home_page-=1
                    elif 258<=tx<=311 and home_page<PAGES-1: _last_act=now; home_page+=1
                elif ty>=GY:
                    col=int((tx-GX)//CW); row=int((ty-GY)//CH); idx=home_page*PER+row*COLS+col
                    if 0<=col<COLS and 0<=row<ROWS and 0<=idx<len(GRID):
                        screen=GRID[idx][0]
                        if screen=='WiFi': wifi_off=0; wifi_t=0.0
                        elif screen=='BLE Scan': ble_page=0; ble_scan_start()
                        elif screen=='Pwnagotchi': pwn_img=None
                        elif screen in NATIVE: run_native(screen); screen='home'
                        elif screen in PLUGINS and hasattr(PLUGINS[screen],'on_enter'):
                            try: PLUGINS[screen].on_enter(CTX)
                            except Exception: pass
            else:
                if screen in LEARN and ty<=26 and 96<=tx<=148:
                    if now-_last_act>0.3: _last_act=now; learn_topic=screen; learn_off=0; screen='learn'
                elif ty<=40 and tx<=160:
                    if screen=='BLE Spam' and ble_spam_running(): ble_spam_stop()
                    if screen=='WiFiKey' and kb_target=='epssid': screen='Evil AP'
                    elif screen in ('WiFiClients','WiFiKey'): screen='WiFi'
                    elif screen=='System': screen='Settings'
                    elif screen=='HWInfo': screen='About'
                    elif screen=='hwref': screen='About'
                    elif screen=='WiFiStatus': screen='Settings'
                    elif screen=='WiFiRoles': screen='Settings'
                    elif screen=='BLE Inspect': screen='BLE Scan'
                    elif screen.startswith('Radar:'): radar_deauth_stop(); radar_blespam_stop(); radar_flipper_stop(); radar_all_stop(); screen='Radar'; radar_img=None
                    elif screen=='learn': screen=learn_topic
                    else:
                        if screen in PLUGINS and hasattr(PLUGINS[screen],'on_exit'):
                            try: PLUGINS[screen].on_exit(CTX)   # release serial port etc.
                            except Exception: pass
                        screen='home'
                elif screen=='About' and 244<=ty<=286 and now-_last_act>0.4:
                    _last_act=now
                    if tx<=232: screen='HWInfo'; hwinfo_collect()
                    elif tx>=248: hwref_open()
                elif screen=='HWInfo' and 286<=ty<=314 and now-_last_act>0.4:
                    _last_act=now; hwref_open()
                elif screen=='hwref' and hwref_blocks is not None and H-24<=ty<=H-2 and now-_last_act>0.2:
                    _htot=max(1,(len(hwref_flat)+HWREF_PER-1)//HWREF_PER)
                    if tx<=120 and hwref_page>0: _last_act=now; hwref_page-=1
                    elif tx>=360 and hwref_page<_htot-1: _last_act=now; hwref_page+=1
                elif screen=='Settings' and 44<=ty<=166:
                    if now-_last_act>0.4: theme='light' if theme=='dark' else 'dark'; apply_theme(theme); save_theme(); _last_act=now
                elif screen=='Settings' and 180<=ty<=224:
                    if now-_last_act>0.4:
                        _last_act=now
                        if tx<240: screen='calibrate'; cal_raws=[]
                        else: screen='System'; svc_refresh()
                elif screen=='Settings' and 232<=ty<=274:
                    if now-_last_act>0.4:
                        _last_act=now
                        if tx<240: screen='WiFiStatus'; radio_rows=[]; wifi_status_scan()
                        else: screen='WiFiRoles'; roles_enter()
                elif screen=='WiFiStatus' and ty<=26 and 96<=tx<=150:
                    if now-_last_act>0.4: _last_act=now; wifi_status_scan()
                elif screen=='WiFiRoles':
                    touch_wifiroles(tx,ty)
                elif screen=='System':
                    if now-_last_act>0.4:
                        hit=False
                        for i,(nm,u) in enumerate(SVC):
                            y=SVC_YY[i]
                            if y<=ty<=y+28 and tx>=300:
                                _last_act=now; sys_confirm=''
                                hdmi_toggle() if u=='acid-hdmi-mirror' else svc_toggle(u)
                                hit=True; break
                        if not hit:
                            if 192<=ty<=222: _last_act=now; sys_confirm=''; restart_os()
                            elif 228<=ty<=258:
                                _last_act=now
                                if sys_confirm=='reboot' and now-sys_confirm_t<5: power_cmd('reboot')
                                else: sys_confirm='reboot'; sys_confirm_t=now
                            elif 264<=ty<=294:
                                _last_act=now
                                if sys_confirm=='shutdown' and now-sys_confirm_t<5: power_cmd('poweroff')
                                else: sys_confirm='shutdown'; sys_confirm_t=now
                elif screen=='WiFi':
                    view=wifi_view()
                    if wifi_confirm:
                        if 146<=ty<=176:
                            if tx<=232:
                                if wifi_confirm=='deauth' and wifi_sel:
                                    deauth_run=True; deauth_macs=set(wifi_sel)
                                    start_deauth([a[5] for a in view if a[5] in wifi_sel])
                                elif wifi_confirm=='connect':
                                    wifi_status='connecting...'; wifi_status_t=now
                                    threading.Thread(target=do_connect,args=(wifi_confirm_ssid,),daemon=True).start()
                                wifi_confirm=None
                            elif tx>=248: wifi_confirm=None
                    elif 30<=ty<=50 and now-_last_act>0.3:
                        _last_act=now
                        if tx<240: wifi_sort={'signal':'channel','channel':'clients','clients':'name','name':'signal'}.get(wifi_sort,'signal')
                        else: wifi_filter={'all':'clients','clients':'all'}.get(wifi_filter,'all')
                        wifi_off=0
                    elif 52<=ty<232:
                        ridx=wifi_off+(ty-52)//30
                        if 0<=ridx<len(view):
                            if tx<28:
                                m=view[ridx][5]
                                if m in wifi_sel: wifi_sel.discard(m)
                                else: wifi_sel.add(m)
                            else: wifi_focus=view[ridx]; screen='WiFiClients'
                    elif 234<=ty<=258:
                        if tx<W//2: wifi_off=max(0,wifi_off-6)
                        else: wifi_off=min(max(0,len(view)-6),wifi_off+6)
                    elif 260<=ty<=300 and now-_last_act>0.3:
                        _last_act=now
                        if tx<90: wifi_sel=set(a[5] for a in view)
                        elif tx<172: wifi_sel=set()
                        elif tx<332:
                            if deauth_run: deauth_run=False; stop_deauth()
                            elif wifi_sel: wifi_confirm='deauth'
                        elif wifi_sel:
                            wifi_confirm_ssid=next((a[0] for a in view if a[5] in wifi_sel),''); kb_pw=''; kb_shift=False; kb_sym=False; kb_target='wifipw'; screen='WiFiKey'
                elif screen=='WiFiClients':
                    if wifi_focus and 84<=ty<236:
                        ci=(ty-84)//26; cls=wifi_focus[6]
                        if 0<=ci<len(cls) and now-_last_act>0.3:
                            deauth_run=True; deauth_macs={wifi_focus[5]}; start_deauth([wifi_focus[5]]); _last_act=now
                    elif 260<=ty<=298 and 120<=tx<=360 and now-_last_act>0.3:
                        deauth_run=True; deauth_macs={wifi_focus[5]}; start_deauth([wifi_focus[5]]); _last_act=now
                elif screen=='Evil AP':
                    if 44<=ty<=69:
                        if now-_last_act>0.3: _last_act=now; kb_target='epssid'; kb_pw=ep_ssid; kb_shift=False; kb_sym=False; screen='WiFiKey'
                    elif 69<ty<=95:
                        if now-_last_act>0.3: _last_act=now; ep_tpl=EP_TPLS[(EP_TPLS.index(ep_tpl)+1)%len(EP_TPLS)] if ep_tpl in EP_TPLS else 'wifi'
                    elif 95<ty<=121:
                        if now-_last_act>0.3:
                            _last_act=now
                            if tx<240: ep_ch={1:6,6:11,11:1}.get(ep_ch,6)
                            else: ep_att=(ep_att%3)+1
                    elif 121<ty<=147:
                        if now-_last_act>0.3: _last_act=now; ep_pass=not ep_pass
                    elif 147<ty<=190:
                        if now-_last_act>0.4:
                            _last_act=now
                            if ep_running(): ep_stop()
                            else: ep_start()
                elif screen=='Handshake':
                    view=wifi_view() if wifi_list else []
                    if 52<=ty<202:
                        ridx=hs_off+(ty-52)//30
                        if 0<=ridx<len(view) and now-_last_act>0.5:
                            _last_act=now; ap=view[ridx]; hs_start(ap[5],ap[1],ap[0])
                    elif 210<=ty<=232:
                        if tx<W//2: hs_off=max(0,hs_off-5)
                        else: hs_off=min(max(0,len(view)-5),hs_off+5)
                    elif 238<=ty<=270 and now-_last_act>0.4:
                        _last_act=now
                        if tx<240: hs_export()
                        else: hs_status='pull *.22000 then: hashcat -m22000 file wordlist'; hs_status_t=now
                elif screen=='BLE Scan':
                    _bcnt=ble_dev_count(); _btot=max(1,(_bcnt+BLE_PER_PAGE-1)//BLE_PER_PAGE)
                    if 34<=ty<=62 and tx<=150 and now-_last_act>0.5:
                        _last_act=now; ble_scan_start()
                    elif _bcnt>BLE_PER_PAGE and H-24<=ty<=H-2 and now-_last_act>0.25:
                        if tx<=120 and ble_page>0: _last_act=now; ble_page-=1
                        elif tx>=360 and ble_page<_btot-1: _last_act=now; ble_page+=1
                    elif 70<=ty<H-26 and now-_last_act>0.3:
                        _idx=int((ty-70)//32); _dv=ble_devices(BLE_PER_PAGE,ble_page*BLE_PER_PAGE)
                        if 0<=_idx<len(_dv):
                            _last_act=now; ble_insp_mac=_dv[_idx][0]; insp_off=0; screen='BLE Inspect'; ble_inspect_start(ble_insp_mac)
                elif screen=='learn':
                    _li=LEARN.get(learn_topic,{}); _ll=3+len(_li.get('how',[]))+len(_li.get('defend',[]))
                    if _ll>LEARN_VIS and H-24<=ty<=H-2 and now-_last_act>0.2:
                        _mo=max(0,_ll-LEARN_VIS); _st=max(1,LEARN_VIS-2)
                        if tx<=120 and learn_off>0: _last_act=now; learn_off=max(0,learn_off-_st)
                        elif tx>=360 and learn_off<_mo: _last_act=now; learn_off=min(_mo,learn_off+_st)
                elif screen=='BLE Inspect':
                    if H-48<=ty<=H-26 and now-_last_act>0.2:
                        _last_act=now
                        if tx<=90: insp_off=max(0,insp_off-8)
                        elif tx>=W-90: insp_off+=8
                elif screen=='Radar':
                    if ty>=54 and now-_last_act>0.3:
                        _c=int((tx-8)//RADAR_CW); _r=int((ty-54)//RADAR_CH); _ri=_r*2+_c
                        if 0<=_c<2 and 0<=_ri<len(RADAR_SUBS) and RADAR_SUBS[_ri][2]=='active':
                            _last_act=now; _rk=RADAR_SUBS[_ri][1]; screen='Radar:'+_rk
                            if _rk=='nearby': ble_scan_start(); radar_ble_t=now
                            elif _rk=='deauth': radar_deauth_start()
                            elif _rk=='blespam': radar_blespam_start()
                            elif _rk=='flipper': radar_flipper_start()
                            elif _rk=='all': radar_all_start()
                elif screen=='BLE Spam':
                    if 38<=ty<=72 and not ble_spam_running() and now-_last_act>0.3:
                        _last_act=now; ble_mode=BLE_MODES[(BLE_MODES.index(ble_mode)+1)%len(BLE_MODES)] if ble_mode in BLE_MODES else 'sink'
                    elif 146<=ty<=190 and now-_last_act>0.4:
                        _last_act=now
                        if ble_spam_running(): ble_spam_stop()
                        else: ble_spam_start()
                elif screen in PLUGINS:
                    try:
                        if hasattr(PLUGINS[screen],'handle_touch'): PLUGINS[screen].handle_touch(tx,ty,CTX)
                    except Exception: pass
                elif screen=='WiFiKey' and now-_last_act>0.15:
                    for ch,x1,y1,x2,y2,kind in kb_keys():
                        if x1<=tx<=x2 and y1<=ty<=y2:
                            _last_act=now
                            if kind=='c': kb_pw=(kb_pw+ch)[:63]
                            elif kind=='space': kb_pw=(kb_pw+' ')[:63]
                            elif kind=='bksp': kb_pw=kb_pw[:-1]
                            elif kind=='shift': kb_shift=not kb_shift
                            elif kind=='sym': kb_sym=not kb_sym
                            elif kind=='cancel': screen=('Evil AP' if kb_target=='epssid' else 'WiFi'); kb_pw=''
                            elif kind=='go':
                                if kb_target=='epssid':
                                    ep_ssid=(kb_pw.strip() or ep_ssid); screen='Evil AP'; kb_pw=''
                                else:
                                    wifi_status='connecting %s...'%wifi_confirm_ssid[:16]; wifi_status_t=now
                                    threading.Thread(target=do_connect,args=(wifi_confirm_ssid,kb_pw),daemon=True).start()
                                    screen='WiFi'; kb_pw=''
                            break
        if screen=='System':
            if now-svc_t>2: svc_refresh(); svc_t=now
            dirty=True
        if screen=='BLE Spam' and ble_spam_running(): dirty=True
        if screen=='BLE Inspect' and ble_insp_status() in ('connecting','enumerating'): dirty=True
        if screen=='Radar:nearby':
            if now-last_draw>=0.1: dirty=True   # ~10fps sweep, easy on the single core
            if not ble_scanning() and now-radar_ble_t>12: ble_scan_start(); radar_ble_t=now
        if screen=='Radar:deauth' and now-last_draw>=0.4: dirty=True
        if screen=='Radar:blespam' and now-last_draw>=0.4: dirty=True
        if screen=='Radar:flipper' and now-last_draw>=0.4: dirty=True
        if screen=='Radar:eviltwin' and now-last_draw>=1.0: dirty=True
        if screen=='Radar:all' and now-last_draw>=0.5: dirty=True
        if screen=='calibrate' or (cal_msg and now-cal_msg_t<6) or (wifi_status and now-wifi_status_t<5): dirty=True
        if screen=='WiFiRoles' and ((roles_confirm and now-roles_confirm_t<4.2) or (roles_status and now-roles_status_t<6)): dirty=True
        if dirty or now-last_draw>=REFRESH:
            dirty=False; last_draw=now
            mi=int(now/3.0)%len(MOODS)
            img=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(img); d._image=img
            if screen=='home': draw_home(d,mi)
            elif screen=='consent': draw_consent(d)
            elif screen=='learn': draw_learn(d)
            elif screen=='About': draw_about(d)
            elif screen=='hwref': draw_hwref(d)
            elif screen=='Radar': draw_radar(d)
            elif screen=='Radar:all': draw_radar_all(d)
            elif screen=='Radar:nearby': draw_radar_nearby(d)
            elif screen=='Radar:deauth': draw_radar_deauth(d)
            elif screen=='Radar:blespam': draw_radar_blespam(d)
            elif screen=='Radar:flipper': draw_radar_flipper(d)
            elif screen=='Radar:eviltwin': draw_radar_eviltwin(d)
            elif screen=='HWInfo': draw_hwinfo(d)
            elif screen=='Settings': draw_settings(d)
            elif screen=='WiFiStatus': draw_wifistatus(d)
            elif screen=='WiFiRoles': draw_wifiroles(d)
            elif screen=='System': draw_system(d)
            elif screen=='calibrate': draw_calibrate(d,len(cal_raws))
            elif screen=='WiFi': draw_wifi(d)
            elif screen=='WiFiClients': draw_wifi_clients(d)
            elif screen=='WiFiKey': draw_wifikey(d)
            elif screen=='Evil AP': draw_evil(d)
            elif screen=='Handshake': draw_handshake(d)
            elif screen=='BLE Scan': draw_ble_scan(d)
            elif screen=='BLE Inspect': draw_ble_inspect(d)
            elif screen=='BLE Spam': draw_ble_spam(d)
            elif screen=='Pwnagotchi': draw_pwnagotchi(d)
            elif screen in PLUGINS:
                try: PLUGINS[screen].draw(d,CTX)
                except Exception: ct(d,W//2,160,'plugin draw error',F_NM,(235,80,80))
            else:
                ap=next((a for a in APPS if a[0]==screen),None)
                if ap: draw_soon(d,ap[0],ap[1],ap[2])
                else: screen='home'; draw_home(d,mi)
            # Bottom footer: the IP/NET bar is HOME-ONLY (on internal screens it would
            # cover PREV/NEXT + UP/DOWN page bars and clip content). The calibration
            # toast stays transient on any screen.
            if screen=='home':
                d.rectangle((0,H-18,W,H),fill=BARBG); d.line([(0,H-18),(W,H-18)],fill=LINE)
                if cal_msg and now-cal_msg_t<6: ct(d,W//2,H-8,cal_msg,F_SM,ACC)
                else:
                    lt(d,10,H-9,'IP '+cur_ip+((' ['+ssh_iface+']') if ssh_iface not in ('','?') else ''),F_SM,(FG if cur_ip!='-' else DIM))
                    if PAGES>1:
                        ct(d,200,H-9,'< PREV',F_SM,(FG if home_page>0 else DIM))
                        ct(d,240,H-9,'%d/%d'%(home_page+1,PAGES),F_SM,ACC)
                        ct(d,283,H-9,'NEXT >',F_SM,(FG if home_page<PAGES-1 else DIM))
                    elif active_radio: ct(d,W//2+20,H-9,('use: '+active_radio)[:24],F_SM,(235,180,40))
                    nc=(25,200,121) if net_state else (235,80,80)
                    d.ellipse((W-94,H-13,W-86,H-5),fill=nc); lt(d,W-80,H-9,'NET '+('ON' if net_state else 'OFF'),F_SM,DIM)
            elif cal_msg and now-cal_msg_t<6:
                d.rectangle((0,H-18,W,H),fill=BARBG); d.line([(0,H-18),(W,H-18)],fill=LINE)
                ct(d,W//2,H-8,cal_msg,F_SM,ACC)
            with open(FB,'wb') as f: f.write(pack(img))
    except Exception: pass
    cnt+=1; time.sleep(TICK)
