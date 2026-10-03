"""Real HTTP integration tests using an isolated, temporary SQLite database."""
import concurrent.futures, http.client, json, secrets, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();server.DB_PATH=Path(cls.tmp.name)/'test.sqlite3';server.init_db()
        cls.password='test-only-'+secrets.token_hex(12);server.create_admin('tester',cls.password)
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.port=cls.http.server_port
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def setUp(self):
        with server.db() as c:
            c.execute('DELETE FROM orders');c.execute('DELETE FROM sessions');c.execute('DELETE FROM attempts')
            c.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(server.DEFAULT_SETTINGS),))
            for p in json.loads((server.ROOT/'products.json').read_text()):c.execute('UPDATE products SET data=? WHERE id=?',(json.dumps(p),p['id']))
        self.cookie='';self.csrf=''
    def call(self,path,method='GET',data=None,origin=True,csrf=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10);headers={'Cookie':self.cookie}
        if data is not None:headers['Content-Type']='application/json'
        if origin:headers['Origin']=f'http://127.0.0.1:{self.port}'
        if csrf:headers['X-CSRF-Token']=self.csrf
        conn.request(method,path,body=json.dumps(data) if data is not None else None,headers=headers)
        r=conn.getresponse();raw=r.read();h=dict(r.getheaders());status=r.status;conn.close()
        return status,json.loads(raw) if 'application/json' in h.get('Content-Type','') else raw,h
    def login(self):
        status,d,h=self.call('/api/admin/login','POST',{'username':'tester','password':self.password});self.assertEqual(status,200);self.cookie=h['Set-Cookie'].split(';')[0];self.csrf=d['csrf']
    def payload(self,kind='inquiry'):
        return {'kind':kind,'customer':{'name':'Test Customer','phone':'+974 5555 1234','email':'test@example.com','address':'Test building','zone':'Test Zone','notes':''},'items':[{'id':'3428460063200','quantity':2,'unit_price':719}],'idempotency_key':secrets.token_hex(16),'expected_total':1938}
    def configure(self,stock=10):
        self.login();p=self.call('/api/admin/products')[1]['products'][0]
        p.update(sale_price=719,selling_unit='1 pouch (100g)',stock=stock,price_confirmed=True)
        self.assertEqual(self.call('/api/admin/products/'+p['id'],'PATCH',p)[0],200)
        s=dict(server.DEFAULT_SETTINGS,orders_enabled=True,delivery_zones=['Test Zone'],delivery_fee=500)
        self.assertEqual(self.call('/api/admin/settings','PATCH',s)[0],200)
    def test_catalog_and_private_files(self):
        status,d,_=self.call('/api/products');self.assertEqual(status,200);self.assertEqual(len(d['products']),84)
        self.assertNotIn('supplier_price',d['products'][0]);self.assertNotIn('source',d['products'][0])
        for path in ['/data/ras.sqlite3','/server.py','/products.json','/static/../server.py']:
            self.assertEqual(self.call(path)[0],404)
    def test_auth_and_csrf(self):
        self.assertEqual(self.call('/api/admin/orders')[0],401);self.login()
        self.assertEqual(self.call('/api/admin/settings','PATCH',server.DEFAULT_SETTINGS,csrf=False)[0],403)
        self.assertEqual(self.call('/api/admin/logout','POST',{},origin=False)[0],403)
        self.assertEqual(self.call('/api/admin/logout','POST',{})[0],200)
        self.assertEqual(self.call('/api/admin/orders')[0],401)
    def test_login_rate_limit(self):
        for _ in range(10):self.assertEqual(self.call('/api/admin/login','POST',{'username':'wrong','password':'wrong'})[0],401)
        self.assertEqual(self.call('/api/admin/login','POST',{'username':'wrong','password':'wrong'})[0],429)
    def test_inquiry_idempotency(self):
        p=self.payload();status,d,_=self.call('/api/orders','POST',p);self.assertEqual(status,201);self.assertIsNone(d['total'])
        status,again,_=self.call('/api/orders','POST',p);self.assertEqual(status,200);self.assertEqual(d['id'],again['id'])
        p['customer']['name']='Different';self.assertEqual(self.call('/api/orders','POST',p)[0],400)
        with server.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],1)
    def test_unconfirmed_order_rejected(self):
        self.assertEqual(self.call('/api/orders','POST',self.payload('order'))[0],400)
    def test_cod_total_stock_and_cancellation(self):
        self.configure();p=self.payload('order');status,d,_=self.call('/api/orders','POST',p);self.assertEqual(status,201);self.assertEqual(d['total'],1938)
        product=self.call('/api/admin/products')[1]['products'][0];self.assertEqual(product['stock'],8)
        self.assertEqual(self.call('/api/admin/orders/'+d['id'],'PATCH',{'status':'cancelled'})[0],200)
        product=self.call('/api/admin/products')[1]['products'][0];self.assertEqual(product['stock'],10)
        self.assertEqual(self.call('/api/admin/orders/'+d['id'],'PATCH',{'status':'cancelled'})[0],400)
    def test_tampered_price_rolls_back(self):
        self.configure();p=self.payload('order');p['expected_total']=1
        self.assertEqual(self.call('/api/orders','POST',p)[0],400)
        self.assertEqual(self.call('/api/admin/products')[1]['products'][0]['stock'],10)
        p['expected_total']=1938;p['items'][0]['unit_price']=1
        self.assertEqual(self.call('/api/orders','POST',p)[0],400)
    def test_stock_concurrency(self):
        self.configure(stock=2)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.call('/api/orders','POST',self.payload('order'))[0],range(2)))
        self.assertEqual(sorted(results),[201,400]);self.assertEqual(self.call('/api/admin/products')[1]['products'][0]['stock'],0)
    def test_delivery_and_validation(self):
        self.configure();p=self.payload('order');p['customer']['zone']='Unsupported';self.assertEqual(self.call('/api/orders','POST',p)[0],400)
        p=self.payload();p['items'][0]['quantity']=True;self.assertEqual(self.call('/api/orders','POST',p)[0],400)
        p=self.payload();p['items']=[1];self.assertEqual(self.call('/api/orders','POST',p)[0],400)
        p=self.payload();p['customer']=[];self.assertEqual(self.call('/api/orders','POST',p)[0],400)
    def test_fulfilment_and_cash(self):
        self.configure();oid=self.call('/api/orders','POST',self.payload('order'))[1]['id'];path='/api/admin/orders/'+oid
        self.assertEqual(self.call(path,'PATCH',{'payment_status':'paid'})[0],400)
        self.assertEqual(self.call(path,'PATCH',{'status':'delivered'})[0],400)
        for status in ['confirmed','packed','delivered']:self.assertEqual(self.call(path,'PATCH',{'status':status})[0],200)
        self.assertEqual(self.call(path,'PATCH',{'payment_status':'paid'})[0],200)
        self.assertEqual(self.call('/api/admin/orders')[1]['orders'][0]['payment_status'],'paid')
    def test_admin_product_and_settings_guards(self):
        self.login();p=self.call('/api/admin/products')[1]['products'][0];p['price_confirmed']=True
        self.assertEqual(self.call('/api/admin/products/'+p['id'],'PATCH',p)[0],400)
        s=dict(server.DEFAULT_SETTINGS,orders_enabled=True);self.assertEqual(self.call('/api/admin/settings','PATCH',s)[0],400)
    def test_security_headers_and_no_order_read(self):
        _,_,h=self.call('/');self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])
        self.assertEqual(self.call('/api/orders')[0],404)
        self.assertEqual(self.call('/api/orders','POST',self.payload(),origin=False)[0],403)

if __name__=='__main__':unittest.main(verbosity=2)
