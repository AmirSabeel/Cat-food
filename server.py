"""Local development server for RAS. Python 3.10+, standard library only."""
import argparse, hashlib, hmac, json, os, re, secrets, sqlite3, time
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('RAS_DB', ROOT / 'data' / 'ras.sqlite3'))
MAX_BODY = 100_000
DEFAULT_SETTINGS = {'store_name':'RAS International Trading WLL','support_email':'sales@rasqatar.com','orders_enabled':False,'delivery_zones':[],'delivery_fee':0,'minimum_order':0}

def db():
    c=sqlite3.connect(DB_PATH, timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c

def init_db():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY,salt TEXT NOT NULL,password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,created TEXT NOT NULL,status TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,idempotency TEXT UNIQUE NOT NULL,request_hash TEXT NOT NULL,stock_reserved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS attempts(bucket TEXT NOT NULL,at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS attempt_lookup ON attempts(bucket,at);
        ''')
        c.execute('INSERT OR IGNORE INTO settings VALUES(1,?)',(json.dumps(DEFAULT_SETTINGS),))
        for p in json.loads((ROOT/'products.json').read_text()):
            c.execute('INSERT OR IGNORE INTO products VALUES(?,?)',(p['id'],json.dumps(p)))
    try: DB_PATH.chmod(0o600)
    except OSError: pass

def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600_000).hex()

def create_admin(username,password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username):raise ValueError('Username must be 3–64 letters, numbers, dots, dashes or underscores.')
    if len(password)<12:raise ValueError('Use a password with at least 12 characters.')
    salt=secrets.token_hex(16)
    with db() as c:
        c.execute('INSERT OR REPLACE INTO admins VALUES(?,?,?)',(username,salt,password_hash(password,salt)))
        c.execute('DELETE FROM sessions WHERE username=?',(username,))

def clean(value,name,maximum=200,required=True):
    if not isinstance(value,str):raise ValueError(f'{name} is required.')
    v=value.strip()
    if (required and not v) or len(v)>maximum:raise ValueError(f'Check {name} (maximum {maximum} characters).')
    return v

def integer(v,name,low=0,high=100_000_000):
    if type(v) is not int or not low<=v<=high:raise ValueError(f'Invalid {name}.')
    return v

def public_product(p):
    return {k:v for k,v in p.items() if k not in ('supplier_box_price','carton_quantity','source','source_page','reference','supplier_price')}

class Handler(BaseHTTPRequestHandler):
    server_version='RASLocal/1.0'
    def log_message(self,format,*args):pass
    def reply(self,status,data,headers=None):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.security_headers()
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def security_headers(self):
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    def body(self):
        if self.headers.get_content_type()!='application/json':raise ValueError('Send application/json.')
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=MAX_BODY:raise ValueError('Request is empty or too large.')
        data=json.loads(self.rfile.read(size))
        if not isinstance(data,dict):raise ValueError('Invalid request.')
        return data
    def same_origin(self):
        origin=self.headers.get('Origin');host=self.headers.get('Host','')
        if not origin or origin not in ('http://'+host,'https://'+host):raise PermissionError('Request origin is not allowed.')
    def session(self,mutation=False):
        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
        token=cookie['ras_session'].value if 'ras_session' in cookie else ''
        with db() as c:s=c.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        if not s:raise PermissionError('Sign in to continue.')
        if mutation and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):raise PermissionError('Session check failed. Refresh and try again.')
        return s
    def throttle(self,bucket,limit,window):
        now=int(time.time());key=bucket+':'+self.client_address[0]
        with db() as c:
            c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM attempts WHERE at<?',(now-3600,))
            n=c.execute('SELECT COUNT(*) FROM attempts WHERE bucket=? AND at>?',(key,now-window)).fetchone()[0]
            if n>=limit:return False
            c.execute('INSERT INTO attempts VALUES(?,?)',(key,now))
        return True
    def do_GET(self):
        path=urlparse(self.path).path
        try:
            if path=='/api/products':
                with db() as c:products=[public_product(json.loads(r['data'])) for r in c.execute('SELECT data FROM products') if json.loads(r['data'])['active']]
                return self.reply(200,{'products':products})
            if path=='/api/settings':
                with db() as c:s=json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
                return self.reply(200,s)
            if path.startswith('/api/admin/'):
                s=self.session()
                if path=='/api/admin/session':return self.reply(200,{'username':s['username'],'csrf':s['csrf']})
                with db() as c:
                    if path=='/api/admin/products':return self.reply(200,{'products':[json.loads(r[0]) for r in c.execute('SELECT data FROM products')]})
                    if path=='/api/admin/orders':
                        orders=[dict(id=r['id'],created=r['created'],status=r['status'],kind=r['kind'],**json.loads(r['data'])) for r in c.execute('SELECT * FROM orders ORDER BY created DESC LIMIT 500')]
                        return self.reply(200,{'orders':orders})
            if path.startswith('/api/'):return self.reply(404,{'error':'Not found.'})
            files={'/':'index.html','/admin':'admin.html','/admin/':'admin.html'}
            target=files.get(path)
            if not target and path.startswith('/static/'):
                candidate=(ROOT/path.lstrip('/')).resolve()
                if candidate.is_relative_to(ROOT/'static') and candidate.is_file():target=str(candidate.relative_to(ROOT))
            if not target:return self.reply(404,{'error':'Not found.'})
            file=ROOT/target
            raw=file.read_bytes();mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.png':'image/png','.jpeg':'image/jpeg','.jpg':'image/jpeg','.webp':'image/webp'}.get(file.suffix,'application/octet-stream')
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-cache');self.security_headers();self.end_headers();self.wfile.write(raw)
        except PermissionError as e:self.reply(401,{'error':str(e)})
        except Exception:self.reply(500,{'error':'Unable to load this page. Please try again.'})
    def do_POST(self):self.mutate('POST')
    def do_PATCH(self):self.mutate('PATCH')
    def mutate(self,method):
        try:
            self.same_origin();data=self.body();path=urlparse(self.path).path
            if path=='/api/admin/login' and method=='POST':return self.login(data)
            if path=='/api/orders' and method=='POST':
                if not self.throttle('checkout',20,3600):return self.reply(429,{'error':'Too many requests. Please try later.'})
                return self.checkout(data)
            if path.startswith('/api/admin/'):
                s=self.session(True)
                if path=='/api/admin/logout' and method=='POST':
                    with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],))
                    return self.reply(200,{'ok':True},{'Set-Cookie':'ras_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict'})
                if path.startswith('/api/admin/products/') and method=='PATCH':return self.product_update(path.rsplit('/',1)[1],data)
                if path=='/api/admin/settings' and method=='PATCH':return self.settings_update(data)
                if path.startswith('/api/admin/orders/') and method=='PATCH':return self.order_update(path.rsplit('/',1)[1],data)
            return self.reply(404,{'error':'Not found.'})
        except PermissionError as e:self.reply(403,{'error':str(e)})
        except (ValueError,TypeError,KeyError,OverflowError) as e:self.reply(400,{'error':str(e) if isinstance(e,ValueError) else 'Invalid request fields.'})
        except Exception:self.reply(500,{'error':'Something went wrong. Please try again.'})
    def login(self,data):
        if not self.throttle('login',10,900):return self.reply(429,{'error':'Too many attempts. Wait 15 minutes.'})
        username=clean(data.get('username'),'username',64);password=data.get('password')
        if not isinstance(password,str) or not 1<=len(password)<=256:raise ValueError('Enter your password.')
        with db() as c:
            user=c.execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone()
            digest=password_hash(password,user['salt'] if user else '00'*16)
            if not user or not hmac.compare_digest(digest,user['password_hash']):return self.reply(401,{'error':'Incorrect username or password.'})
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24);now=int(time.time())
            c.execute('DELETE FROM sessions WHERE expires<=?',(now,));c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,csrf,now+28800))
        secure='; Secure' if os.environ.get('RAS_SECURE_COOKIES')=='1' else ''
        return self.reply(200,{'username':username,'csrf':csrf},{'Set-Cookie':f'ras_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800{secure}'})
    def product_update(self,pid,data):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
            if not row:return self.reply(404,{'error':'Product not found.'})
            p=json.loads(row[0]);p['name']=clean(data.get('name'),'product name',240)
            p['sale_price']=integer(data.get('sale_price'),'price in minor units',1) if data.get('sale_price') is not None else None
            p['stock']=integer(data.get('stock'),'stock',0,1000000)
            p['selling_unit']=clean(data.get('selling_unit',''),'selling unit',80,False)
            for field in ('active','price_confirmed'):
                if type(data.get(field)) is not bool:raise ValueError('Invalid '+field)
                p[field]=data[field]
            if p['price_confirmed'] and (p['sale_price'] is None or not p['selling_unit']):raise ValueError('Set a QAR price and selling unit before confirming.')
            c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),pid))
        return self.reply(200,{'product':p})
    def settings_update(self,data):
        s=DEFAULT_SETTINGS.copy();s['store_name']=clean(data.get('store_name'),'store name',120)
        s['support_email']=clean(data.get('support_email'),'email',200)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',s['support_email']):raise ValueError('Enter a valid support email.')
        zones=data.get('delivery_zones')
        if not isinstance(zones,list) or len(zones)>50:raise ValueError('Invalid delivery zones.')
        s['delivery_zones']=list(dict.fromkeys(clean(z,'zone',80) for z in zones))
        s['delivery_fee']=integer(data.get('delivery_fee'),'delivery fee')
        s['minimum_order']=integer(data.get('minimum_order'),'minimum order')
        if type(data.get('orders_enabled')) is not bool:raise ValueError('Invalid order setting.')
        s['orders_enabled']=data['orders_enabled']
        if s['orders_enabled'] and not zones:raise ValueError('Add delivery zones before enabling cash-on-delivery orders.')
        with db() as c:c.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(s),))
        return self.reply(200,s)
    def checkout(self,data):
        key=clean(data.get('idempotency_key'),'request key',100)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):raise ValueError('Invalid request key.')
        request_hash=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM orders WHERE idempotency=?',(key,)).fetchone()
            if old:
                if old['request_hash']!=request_hash:raise ValueError('Request already used. Start a new checkout.')
                stored=json.loads(old['data']);return self.reply(200,{'id':old['id'],'kind':old['kind'],'total':stored.get('total'),'duplicate':True})
            kind=data.get('kind')
            if kind not in ('inquiry','order'):raise ValueError('Invalid request type.')
            customer=data.get('customer',{})
            if not isinstance(customer,dict):raise ValueError('Invalid customer details.')
            customer={k:clean(customer.get(k,''),k,limit,k in ('name','phone')) for k,limit in [('name',100),('phone',30),('email',200),('address',500),('zone',80),('notes',1000)]}
            if not re.fullmatch(r'[+\d\s()-]{7,30}',customer['phone']) or len(re.sub(r'\D','',customer['phone']))<7:raise ValueError('Enter a valid phone number.')
            if customer['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',customer['email']):raise ValueError('Enter a valid email address.')
            settings=json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
            items=data.get('items')
            if not isinstance(items,list) or not 1<=len(items)<=84:raise ValueError('Your cart is empty or too large.')
            records=[];seen=set();subtotal=0
            for item in items:
                if not isinstance(item,dict):raise ValueError('Invalid cart item.')
                pid=clean(item.get('id'),'product',30);qty=integer(item.get('quantity'),'quantity',1,99)
                if pid in seen:raise ValueError('Duplicate product in cart.')
                seen.add(pid);row=c.execute('SELECT data FROM products WHERE id=?',(pid,)).fetchone()
                if not row:raise ValueError('A product is no longer available.')
                p=json.loads(row[0])
                if not p['active']:raise ValueError('A product is no longer available.')
                if kind=='order':
                    if not p['price_confirmed'] or p['sale_price'] is None:raise ValueError('A product needs price confirmation. Submit an enquiry instead.')
                    if qty>p['stock']:raise ValueError('Not enough stock for '+p['name'])
                    if item.get('unit_price')!=p['sale_price']:raise ValueError('A price has changed. Refresh your cart.')
                    subtotal+=p['sale_price']*qty
                    p['stock']-=qty;c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),pid))
                records.append({'id':pid,'name':p['name'],'quantity':qty,'selling_unit':p['selling_unit'],'unit_price':p['sale_price'] if p['price_confirmed'] else None})
            fee=None;total=None
            if kind=='order':
                if not settings['orders_enabled']:raise ValueError('Ordering is not enabled yet. Submit an enquiry instead.')
                if not customer['address'] or customer['zone'] not in settings['delivery_zones']:raise ValueError('Enter an address and a supported delivery zone.')
                if subtotal<settings['minimum_order']:raise ValueError('The order is below the minimum order amount.')
                fee=settings['delivery_fee'];total=subtotal+fee
                if data.get('expected_total')!=total:raise ValueError('The order total has changed. Refresh checkout.')
            oid='RAS-'+secrets.token_hex(6).upper();created=datetime.now(timezone.utc).isoformat()
            saved={'customer':customer,'items':records,'subtotal':subtotal if kind=='order' else None,'delivery_fee':fee,'total':total,'payment_method':'cash_on_delivery' if kind=='order' else None,'payment_status':'unpaid' if kind=='order' else 'not_applicable'}
            c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)',(oid,created,'new' if kind=='order' else 'inquiry',kind,json.dumps(saved),key,request_hash,int(kind=='order')))
        return self.reply(201,{'id':oid,'kind':kind,'total':total})
    def order_update(self,oid,data):
        transitions={'inquiry':{'reviewed','cancelled'},'reviewed':{'cancelled'},'new':{'confirmed','cancelled'},'confirmed':{'packed','cancelled'},'packed':{'delivered','cancelled'},'delivered':set(),'cancelled':set()}
        status=data.get('status')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not row:return self.reply(404,{'error':'Order not found.'})
            if data.get('payment_status')=='paid':
                if row['kind']!='order' or row['status']!='delivered':raise ValueError('Cash collection can only be recorded for delivered orders.')
                saved=json.loads(row['data']);saved['payment_status']='paid'
                c.execute('UPDATE orders SET data=? WHERE id=?',(json.dumps(saved),oid))
                c.commit()
                return self.reply(200,{'id':oid,'payment_status':'paid'})
            if status not in transitions.get(row['status'],set()):raise ValueError('This status transition is not allowed.')
            reserved=row['stock_reserved']
            if status=='cancelled' and reserved:
                for item in json.loads(row['data'])['items']:
                    p=json.loads(c.execute('SELECT data FROM products WHERE id=?',(item['id'],)).fetchone()[0]);p['stock']+=item['quantity'];c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),p['id']))
                reserved=0
            c.execute('UPDATE orders SET status=?,stock_reserved=? WHERE id=?',(status,reserved,oid))
        return self.reply(200,{'id':oid,'status':status})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8000);parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    init_db();print(f'RAS development server: http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
