import os, sqlite3, secrets, sys
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    # Keep writable user data outside the installation directory.
    DB_DEFAULT_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'M-ERP')
    os.makedirs(DB_DEFAULT_DIR, exist_ok=True)
else:
    DB_DEFAULT_DIR = BASE
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(DB_DEFAULT_DIR, 'almuradi.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE','0') == '1',
                  PERMANENT_SESSION_LIFETIME=__import__('datetime').timedelta(hours=8))

def connect_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    c = connect_db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'admin');
    CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, opening_balance REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '', address TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL, invoice_date TEXT NOT NULL, kind TEXT NOT NULL, party_id INTEGER, description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0), status TEXT NOT NULL DEFAULT 'غير مدفوعة', created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(party_id) REFERENCES parties(id));
    CREATE TABLE IF NOT EXISTS journal_entries(id INTEGER PRIMARY KEY, entry_date TEXT NOT NULL, reference TEXT DEFAULT '', description TEXT NOT NULL, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(created_by) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS journal_lines(id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL, account_id INTEGER NOT NULL, debit REAL NOT NULL DEFAULT 0 CHECK(debit>=0), credit REAL NOT NULL DEFAULT 0 CHECK(credit>=0), FOREIGN KEY(entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE, FOREIGN KEY(account_id) REFERENCES accounts(id));
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, details TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT DEFAULT '', unit TEXT DEFAULT 'قطعة', cost REAL NOT NULL DEFAULT 0 CHECK(cost>=0), price REAL NOT NULL DEFAULT 0 CHECK(price>=0), quantity REAL NOT NULL DEFAULT 0 CHECK(quantity>=0), min_quantity REAL NOT NULL DEFAULT 0 CHECK(min_quantity>=0), active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, expense_date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0), payment_method TEXT DEFAULT 'نقدًا', reference TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'إشعار', active INTEGER NOT NULL DEFAULT 1, created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(created_by) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS stock_moves(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, move_date TEXT NOT NULL, move_type TEXT NOT NULL, quantity REAL NOT NULL CHECK(quantity>0), notes TEXT DEFAULT '', user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(product_id) REFERENCES products(id), FOREIGN KEY(user_id) REFERENCES users(id));
    ''')
    if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
        c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)', ('admin', generate_password_hash(os.environ.get('INITIAL_ADMIN_PASSWORD', 'ChangeMe123!')), 'admin'))
    if not c.execute('SELECT id FROM accounts LIMIT 1').fetchone():
        c.executemany('INSERT INTO accounts(code,name,category,opening_balance) VALUES(?,?,?,?)', [
            ('1000','الصندوق','أصول',0),('1010','البنك','أصول',0),('1100','العملاء','أصول',0),('1200','المخزون','أصول',0),
            ('2000','الموردون','خصوم',0),('2100','ضريبة مستحقة','خصوم',0),('3000','رأس المال','حقوق ملكية',0),
            ('4000','إيرادات المبيعات','إيرادات',0),('4100','إيرادات الخدمات البرمجية','إيرادات',0),('5000','مصروفات التشغيل','مصروفات',0)])
    c.commit(); c.close()

# Initialize schema on import so production WSGI servers also have a database.
init_db()

@app.before_request
def before_request():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    if request.method == 'POST':
        submitted = request.form.get('_csrf_token', '')
        expected = session.get('_csrf_token', '')
        import hmac
        if not submitted or not expected or not hmac.compare_digest(submitted, expected):
            return 'طلب غير صالح أو انتهت الجلسة. حدّث الصفحة وحاول مجددًا.', 400
    g.db = connect_db()

@app.teardown_appcontext
def teardown(error=None):
    c = g.pop('db', None)
    if c is not None: c.close()

@app.context_processor
def context(): return {'today': date.today().isoformat(), 'current_user': session.get('username')}

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get('user_id'): return redirect(url_for('login'))
        return fn(*a, **kw)
    return wrapped

def audit(action, details=''):
    g.db.execute('INSERT INTO audit_log(user_id,action,details) VALUES(?,?,?)', (session.get('user_id'), action, details))

@app.route('/')
def index():
    # Branded welcome screen is shown on each fresh visit; Continue opens the system.
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return render_template('welcome.html')

@app.route('/continue')
def continue_to_login():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = g.db.execute('SELECT * FROM users WHERE username=?', (request.form.get('username','').strip(),)).fetchone()
        if u and check_password_hash(u['password_hash'], request.form.get('password','')):
            session.clear(); session['user_id']=u['id']; session['username']=u['username']; session['role']=u['role']
            audit('login','Successful login'); g.db.commit()
            return redirect(url_for('dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    d=g.db
    metrics={
      'accounts':d.execute('SELECT COUNT(*) n FROM accounts WHERE active=1').fetchone()['n'],
      'parties':d.execute('SELECT COUNT(*) n FROM parties').fetchone()['n'],
      'invoices':d.execute('SELECT COUNT(*) n FROM invoices').fetchone()['n'],
      'sales':d.execute("SELECT COALESCE(SUM(amount),0) n FROM invoices WHERE kind='مبيعات'").fetchone()['n'],
      'purchases':d.execute("SELECT COALESCE(SUM(amount),0) n FROM invoices WHERE kind='مشتريات'").fetchone()['n']}
    recent=d.execute('SELECT * FROM journal_entries ORDER BY id DESC LIMIT 8').fetchall()
    return render_template('dashboard.html', metrics=metrics, recent=recent, page='dashboard')

@app.route('/accounts', methods=['GET','POST'])
@login_required
def accounts():
    if request.method=='POST':
        try:
            g.db.execute('INSERT INTO accounts(code,name,category,opening_balance) VALUES(?,?,?,?)', (request.form['code'].strip(),request.form['name'].strip(),request.form['category'],float(request.form.get('opening_balance') or 0)))
            audit('account_created', request.form['code']); g.db.commit(); flash('تمت إضافة الحساب بنجاح.','success')
        except sqlite3.IntegrityError: flash('رمز الحساب مستخدم مسبقًا.','error')
        except (ValueError, KeyError): flash('تحقق من البيانات المدخلة.','error')
        return redirect(url_for('accounts'))
    rows=g.db.execute('''SELECT a.*,(SELECT COALESCE(SUM(debit),0) FROM journal_lines WHERE account_id=a.id) debit,(SELECT COALESCE(SUM(credit),0) FROM journal_lines WHERE account_id=a.id) credit FROM accounts a WHERE active=1 ORDER BY code''').fetchall()
    return render_template('accounts.html',rows=rows,page='accounts')

@app.route('/parties', methods=['GET','POST'])
@login_required
def parties():
    if request.method=='POST':
        g.db.execute('INSERT INTO parties(name,kind,phone,email,address) VALUES(?,?,?,?,?)',(request.form['name'].strip(),request.form['kind'],request.form.get('phone',''),request.form.get('email',''),request.form.get('address','')))
        audit('party_created',request.form['name']); g.db.commit(); flash('تم حفظ العميل أو المورد.','success'); return redirect(url_for('parties'))
    rows=g.db.execute('SELECT * FROM parties ORDER BY id DESC').fetchall()
    return render_template('parties.html',rows=rows,page='parties')

@app.route('/invoices', methods=['GET','POST'])
@login_required
def invoices():
    if request.method=='POST':
        try:
            amount=float(request.form['amount'])
            if amount<=0: raise ValueError
            g.db.execute('INSERT INTO invoices(number,invoice_date,kind,party_id,description,amount,status) VALUES(?,?,?,?,?,?,?)',(request.form['number'].strip(),request.form['invoice_date'],request.form['kind'],request.form.get('party_id') or None,request.form['description'].strip(),amount,request.form['status']))
            audit('invoice_created',request.form['number']); g.db.commit(); flash('تم حفظ الفاتورة. ملاحظة: لا تُرحّل الفواتير تلقائيًا إلى دفتر اليومية في هذه النسخة.','success')
        except sqlite3.IntegrityError: flash('رقم الفاتورة مكرر أو الطرف غير صحيح.','error')
        except (ValueError,KeyError): flash('أدخل مبلغًا صحيحًا أكبر من صفر.','error')
        return redirect(url_for('invoices'))
    rows=g.db.execute('SELECT i.*,p.name party_name FROM invoices i LEFT JOIN parties p ON p.id=i.party_id ORDER BY i.id DESC').fetchall()
    parties_list=g.db.execute('SELECT * FROM parties ORDER BY name').fetchall()
    return render_template('invoices.html',rows=rows,parties=parties_list,page='invoices')

@app.route('/entries', methods=['GET','POST'])
@login_required
def entries():
    if request.method=='POST':
        try:
            ids=request.form.getlist('account_id[]'); ds=request.form.getlist('debit[]'); cs=request.form.getlist('credit[]'); lines=[]
            if not (len(ids)==len(ds)==len(cs)): raise ValueError
            for aid,d,c in zip(ids,ds,cs):
                d=float(d or 0); c=float(c or 0)
                if d<0 or c<0 or (d>0 and c>0): raise ValueError
                if d or c: lines.append((int(aid),d,c))
            if len(lines)<2 or round(sum(x[1] for x in lines),2)!=round(sum(x[2] for x in lines),2) or sum(x[1] for x in lines)<=0:
                flash('يجب إدخال سطرين على الأقل، مع تساوي إجمالي المدين والدائن.','error'); return redirect(url_for('entries'))
            cur=g.db.execute('INSERT INTO journal_entries(entry_date,reference,description,created_by) VALUES(?,?,?,?)',(request.form['entry_date'],request.form.get('reference',''),request.form['description'].strip(),session['user_id']))
            for aid,d,c in lines: g.db.execute('INSERT INTO journal_lines(entry_id,account_id,debit,credit) VALUES(?,?,?,?)',(cur.lastrowid,aid,d,c))
            audit('journal_entry_created',request.form.get('reference','')); g.db.commit(); flash('تم حفظ القيد المتوازن بنجاح.','success')
        except (ValueError,KeyError): flash('تحقق من بيانات القيد والمبالغ.','error')
        return redirect(url_for('entries'))
    accts=g.db.execute('SELECT * FROM accounts WHERE active=1 ORDER BY code').fetchall()
    rows=g.db.execute('''SELECT e.*,COALESCE(SUM(l.debit),0) debit,COALESCE(SUM(l.credit),0) credit,GROUP_CONCAT(a.name,'، ') accounts FROM journal_entries e LEFT JOIN journal_lines l ON l.entry_id=e.id LEFT JOIN accounts a ON a.id=l.account_id GROUP BY e.id ORDER BY e.id DESC''').fetchall()
    return render_template('entries.html',accounts=accts,rows=rows,page='entries')

@app.route('/reports')
@login_required
def reports():
    rows=g.db.execute('''SELECT a.code,a.name,a.category,a.opening_balance,COALESCE(SUM(l.debit),0) debit,COALESCE(SUM(l.credit),0) credit FROM accounts a LEFT JOIN journal_lines l ON l.account_id=a.id WHERE a.active=1 GROUP BY a.id ORDER BY a.code''').fetchall()
    debit=sum(r['debit'] for r in rows); credit=sum(r['credit'] for r in rows)
    sales=g.db.execute("SELECT COALESCE(SUM(amount),0) n FROM invoices WHERE kind='مبيعات'").fetchone()['n']
    purchases=g.db.execute("SELECT COALESCE(SUM(amount),0) n FROM invoices WHERE kind='مشتريات'").fetchone()['n']
    return render_template('reports.html',rows=rows,debit=debit,credit=credit,sales=sales,purchases=purchases,page='reports')

@app.route('/audit')
@login_required
def audit_page():
    if session.get('role')!='admin': flash('هذه الصفحة متاحة للمدير فقط.','error'); return redirect(url_for('dashboard'))
    rows=g.db.execute('SELECT a.*,u.username FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 250').fetchall()
    return render_template('audit.html',rows=rows,page='audit')

@app.route('/announcements', methods=['GET','POST'])
@login_required
def announcements():
    if session.get('role') != 'admin':
        flash('هذه الصفحة متاحة للمدير فقط.', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        action=request.form.get('action','create')
        if action == 'delete':
            aid=request.form.get('id','')
            g.db.execute('DELETE FROM announcements WHERE id=?',(aid,)); audit('announcement_deleted',str(aid)); g.db.commit(); flash('تم حذف الإعلان.','success')
        elif action == 'toggle':
            aid=request.form.get('id',''); g.db.execute('UPDATE announcements SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?',(aid,)); audit('announcement_toggled',str(aid)); g.db.commit(); flash('تم تحديث حالة الإعلان.','success')
        else:
            title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); kind=request.form.get('kind','إشعار')
            if title and body:
                g.db.execute('INSERT INTO announcements(title,body,kind,created_by) VALUES(?,?,?,?)',(title,body,kind,session.get('user_id'))); audit('announcement_created',title); g.db.commit(); flash('تم نشر الإشعار/الإعلان.','success')
            else: flash('أدخل العنوان والمحتوى.','error')
        return redirect(url_for('announcements'))
    rows=g.db.execute('SELECT * FROM announcements ORDER BY id DESC').fetchall()
    return render_template('announcements.html',rows=rows,page='announcements')

@app.route('/health')
def health(): return {'status':'ok','application':'ALMURADI SOFT Accounting'}


@app.route('/products', methods=['GET','POST'])
@login_required
def products():
    if request.method == 'POST':
        try:
            sku=request.form.get('sku','').strip(); name=request.form.get('name','').strip()
            cost=float(request.form.get('cost') or 0); price=float(request.form.get('price') or 0)
            qty=float(request.form.get('quantity') or 0); minimum=float(request.form.get('min_quantity') or 0)
            if not sku or not name or min(cost,price,qty,minimum)<0: raise ValueError
            g.db.execute('INSERT INTO products(sku,name,category,unit,cost,price,quantity,min_quantity) VALUES(?,?,?,?,?,?,?,?)',
                (sku,name,request.form.get('category','').strip(),request.form.get('unit','قطعة').strip(),cost,price,qty,minimum))
            audit('product_created',sku); g.db.commit(); flash('تمت إضافة الصنف بنجاح.','success')
        except sqlite3.IntegrityError: flash('رمز الصنف مستخدم من قبل.','error')
        except (ValueError,KeyError): flash('تحقق من البيانات والكميات والأسعار.','error')
        return redirect(url_for('products'))
    rows=g.db.execute('SELECT * FROM products WHERE active=1 ORDER BY name').fetchall()
    return render_template('products.html',rows=rows,page='products')

@app.route('/stock/<int:product_id>', methods=['POST'])
@login_required
def stock_move(product_id):
    try:
        qty=float(request.form.get('quantity') or 0); typ=request.form.get('move_type')
        product=g.db.execute('SELECT * FROM products WHERE id=? AND active=1',(product_id,)).fetchone()
        if not product or qty<=0 or typ not in ('إضافة','صرف'): raise ValueError
        if typ=='صرف' and qty>product['quantity']:
            flash('الكمية المطلوبة أكبر من المخزون المتاح.','error'); return redirect(url_for('products'))
        new_qty=product['quantity']+qty if typ=='إضافة' else product['quantity']-qty
        g.db.execute('UPDATE products SET quantity=? WHERE id=?',(new_qty,product_id))
        g.db.execute('INSERT INTO stock_moves(product_id,move_date,move_type,quantity,notes,user_id) VALUES(?,?,?,?,?,?)',
            (product_id,date.today().isoformat(),typ,qty,request.form.get('notes',''),session['user_id']))
        audit('stock_move',f"{product['sku']} {typ} {qty}"); g.db.commit(); flash('تم تحديث المخزون وتسجيل الحركة.','success')
    except (ValueError,TypeError): flash('بيانات حركة المخزون غير صحيحة.','error')
    return redirect(url_for('products'))

@app.route('/expenses', methods=['GET','POST'])
@login_required
def expenses():
    if request.method=='POST':
        try:
            amount=float(request.form.get('amount') or 0)
            if amount<=0: raise ValueError
            category=request.form.get('category','').strip(); desc=request.form.get('description','').strip()
            if not category or not desc: raise ValueError
            g.db.execute('INSERT INTO expenses(expense_date,category,description,amount,payment_method,reference) VALUES(?,?,?,?,?,?)',
                (request.form.get('expense_date') or date.today().isoformat(),category,desc,amount,request.form.get('payment_method','نقدًا'),request.form.get('reference','').strip()))
            audit('expense_created',desc); g.db.commit(); flash('تم تسجيل المصروف.','success')
        except (ValueError,TypeError): flash('أدخل بيانات مصروف صحيحة.','error')
        return redirect(url_for('expenses'))
    rows=g.db.execute('SELECT * FROM expenses ORDER BY expense_date DESC,id DESC').fetchall()
    total=g.db.execute('SELECT COALESCE(SUM(amount),0) n FROM expenses').fetchone()['n']
    return render_template('expenses.html',rows=rows,total=total,page='expenses')

@app.route('/users', methods=['GET','POST'])
@login_required
def users():
    if session.get('role')!='admin': flash('إدارة المستخدمين للمدير فقط.','error'); return redirect(url_for('dashboard'))
    if request.method=='POST':
        try:
            username=request.form.get('username','').strip(); password=request.form.get('password','')
            role=request.form.get('role','staff')
            if len(username)<3 or len(password)<12 or role not in ('admin','accountant','staff'): raise ValueError
            g.db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,generate_password_hash(password),role))
            audit('user_created',username); g.db.commit(); flash('تم إنشاء المستخدم.','success')
        except sqlite3.IntegrityError: flash('اسم المستخدم موجود بالفعل.','error')
        except (ValueError,KeyError): flash('اسم المستخدم 3 أحرف على الأقل وكلمة المرور 12 حرفًا على الأقل.','error')
        return redirect(url_for('users'))
    rows=g.db.execute('SELECT id,username,role FROM users ORDER BY id').fetchall()
    return render_template('users.html',rows=rows,page='users')

@app.route('/backup')
@login_required
def backup():
    if session.get('role')!='admin': flash('النسخ الاحتياطي للمدير فقط.','error'); return redirect(url_for('dashboard'))
    from flask import send_file
    import io
    out=io.BytesIO()
    # SQLite backup into a temporary file to make a valid downloadable database.
    import tempfile
    fd,path=tempfile.mkstemp(prefix='almuradi_backup_',suffix='.db'); os.close(fd)
    try:
        disk=sqlite3.connect(path); g.db.backup(disk); disk.close()
        audit('database_backup','Database backup downloaded'); g.db.commit()
        return send_file(path,as_attachment=True,download_name=f'almuradi_backup_{date.today().isoformat()}.db',mimetype='application/octet-stream')
    except Exception:
        try: os.unlink(path)
        except OSError: pass
        raise

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method=='POST':
        theme=request.form.get('theme','light')
        accent=request.form.get('accent','#147d64')
        if theme not in ('light','dark'): theme='light'
        if accent not in ('#147d64','#2457c5','#7c3aed','#b45309','#be123c'): accent='#147d64'
        session['theme']=theme; session['accent']=accent
        flash('تم حفظ تفضيلات الواجهة لهذا المتصفح.','success')
        return redirect(url_for('settings'))
    return render_template('settings.html',page='settings')

@app.route('/export/invoices.csv')
@login_required
def export_invoices():
    import csv, io
    from flask import Response
    data=io.StringIO(); writer=csv.writer(data)
    writer.writerow(['number','date','kind','party','description','amount','status'])
    rows=g.db.execute('SELECT i.number,i.invoice_date,i.kind,p.name,i.description,i.amount,i.status FROM invoices i LEFT JOIN parties p ON p.id=i.party_id ORDER BY i.id').fetchall()
    for r in rows: writer.writerow(list(r))
    audit('invoices_exported',f'{len(rows)} invoices'); g.db.commit()
    return Response('\ufeff'+data.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=invoices.csv'})



# Controlled CRUD endpoints for editable master data and unposted records.
CRUD_FIELDS = {
    'products': {'sku','name','category','unit','cost','price','quantity','min_quantity'},
    'parties': {'name','kind','phone','email','address'},
    'accounts': {'code','name','category','opening_balance'},
    'expenses': {'expense_date','category','description','amount','payment_method','reference'},
    'invoices': {'number','invoice_date','kind','party_id','description','amount','status'},
}
CRUD_NUMERIC = {
    'products': {'cost','price','quantity','min_quantity'},
    'accounts': {'opening_balance'}, 'expenses': {'amount'}, 'invoices': {'amount'}
}
CRUD_LABELS = {'products':'الأصناف','parties':'العملاء والموردون','accounts':'الحسابات','expenses':'المصروفات','invoices':'الفواتير'}

@app.route('/manage/<entity>/<int:record_id>/<action>', methods=['GET','POST'])
@login_required
def manage_record(entity, record_id, action):
    if entity not in CRUD_FIELDS or action not in ('edit','delete'):
        return render_template('error.html', code=404, message='العملية المطلوبة غير متاحة.'), 404
    if session.get('role') not in ('admin','accountant'):
        flash('ليست لديك صلاحية لتنفيذ هذه العملية.','error'); return redirect(url_for('dashboard'))
    table=entity
    row=g.db.execute(f'SELECT * FROM {table} WHERE id=?',(record_id,)).fetchone()
    if not row:
        flash('السجل غير موجود.','error'); return redirect(url_for(entity))
    if action=='delete' and request.method=='POST':
        try:
            # Prevent destructive deletion when records are referenced by accounting activity.
            if entity=='accounts' and g.db.execute('SELECT 1 FROM journal_lines WHERE account_id=? LIMIT 1',(record_id,)).fetchone():
                flash('لا يمكن حذف حساب مرتبط بقيود؛ عطّله أو استخدم حسابًا بديلًا.','error')
            elif entity=='parties' and g.db.execute('SELECT 1 FROM invoices WHERE party_id=? LIMIT 1',(record_id,)).fetchone():
                flash('لا يمكن حذف طرف مرتبط بفواتير.','error')
            elif entity=='products':
                g.db.execute('UPDATE products SET active=0 WHERE id=?',(record_id,)); audit('product_archived',str(record_id)); g.db.commit(); flash('تمت أرشفة الصنف.','success')
            else:
                g.db.execute(f'DELETE FROM {table} WHERE id=?',(record_id,)); audit(f'{entity}_deleted',str(record_id)); g.db.commit(); flash('تم الحذف بنجاح.','success')
        except sqlite3.IntegrityError:
            g.db.rollback(); flash('تعذر الحذف لوجود ارتباطات في قاعدة البيانات.','error')
        return redirect(url_for(entity))
    if action=='edit' and request.method=='POST':
        try:
            fields=CRUD_FIELDS[entity]
            values=[]
            for field in fields:
                raw=request.form.get(field, str(row[field] if row[field] is not None else '')).strip()
                if field in CRUD_NUMERIC.get(entity,set()):
                    value=float(raw or 0)
                    if value < 0 or (entity in ('expenses','invoices') and field=='amount' and value<=0): raise ValueError
                elif field=='party_id': value=int(raw) if raw else None
                else: value=raw
                values.append(value)
            assignments=','.join(f'{f}=?' for f in fields)
            g.db.execute(f'UPDATE {table} SET {assignments} WHERE id=?',(*values,record_id))
            audit(f'{entity}_updated',str(record_id)); g.db.commit(); flash('تم تحديث السجل بنجاح.','success'); return redirect(url_for(entity))
        except (ValueError,sqlite3.IntegrityError):
            g.db.rollback(); flash('تعذر التحديث: تحقق من القيم وعدم تكرار الرمز أو الرقم.','error')
    parties=[]
    if entity=='invoices': parties=g.db.execute('SELECT id,name FROM parties ORDER BY name').fetchall()
    return render_template('record_edit.html',entity=entity,entity_label=CRUD_LABELS[entity],row=row,fields=CRUD_FIELDS[entity],parties=parties,page=entity)


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html',code=404,message='الصفحة المطلوبة غير موجودة.'),404

@app.errorhandler(500)
def server_error(error):
    app.logger.exception('Unhandled application error')
    return render_template('error.html',code=500,message='حدث خطأ داخلي. راجع سجل التشغيل.'),500


if __name__=='__main__':
    import threading, webbrowser
    init_db()
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8000'))
    print(f'ALMURADI SOFT ERP is running at http://{host}:{port}')
    if host in ('127.0.0.1','localhost') and os.environ.get('NO_BROWSER_OPEN') != '1':
        threading.Timer(1.2, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    app.run(host=host,port=port,debug=False)
