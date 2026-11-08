"""Document-scoped research allowance, durable reservations, and reusable evidence."""
import json
import math
from decimal import Decimal
from . import db
from .generation_errors import GenerationError

class ResearchPaused(GenerationError):
    def __init__(self,reason,message,required_usd=None):super().__init__(message);self.reason=reason;self.required_usd=required_usd


def migrate(connection):
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS generator_research_budgets(document_id TEXT PRIMARY KEY REFERENCES generator_documents(id),limit_usd REAL NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS generator_research_ops(document_id TEXT NOT NULL REFERENCES generator_documents(id),identity TEXT NOT NULL,job_id TEXT NOT NULL,call_key TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,reserved REAL NOT NULL,estimated REAL,result TEXT,usage TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,PRIMARY KEY(document_id,identity));
    CREATE TABLE IF NOT EXISTS generator_research_cache(document_id TEXT NOT NULL,identity TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(document_id,identity));
    CREATE TABLE IF NOT EXISTS generator_research_budget_log(document_id TEXT NOT NULL,old_limit REAL,new_limit REAL NOT NULL,created_at TEXT NOT NULL);
    ''')
    if not connection.execute("SELECT 1 FROM generator_meta WHERE key='research_defaults_v2'").fetchone():
        with db.transaction(connection):
            connection.execute("UPDATE generator_settings SET config=json_set(config,'$.web_search',json('true'),'$.web_budget_usd',5.0),revision=revision+1 WHERE id=1")
            connection.execute("INSERT OR IGNORE INTO generator_meta VALUES('research_defaults_v2','1')")


def valid_limit(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1000


def ensure_budget(connection,document_id,limit=5):
    connection.execute('INSERT OR IGNORE INTO generator_research_budgets VALUES(?,?,?)',(document_id,limit,db.now()))


def summary(connection,document_id):
    row=connection.execute('SELECT limit_usd FROM generator_research_budgets WHERE document_id=?',(document_id,)).fetchone()
    limit=row['limit_usd'] if row else 5.0
    ops=connection.execute('SELECT kind,status,reserved,estimated,usage FROM generator_research_ops WHERE document_id=?',(document_id,)).fetchall()
    spent=sum(Decimal(str(op['estimated'])) for op in ops if op['estimated'] is not None)
    reserved=sum(Decimal(str(op['reserved'])) for op in ops if op['estimated'] is None and op['status']!='rejected')
    legacy=connection.execute("""SELECT c.cost,c.cost_known,c.reserved_cost,c.status FROM generator_calls c JOIN generator_jobs j ON j.id=c.job_id
        WHERE j.document_id=? AND (c.budget_scope='web' OR c.stage LIKE 'web-research:%')""",(document_id,)).fetchall()
    spent+=sum(Decimal(str(op['cost'])) for op in legacy if op['cost_known'])
    reserved+=sum(Decimal(str(op['reserved_cost'])) for op in legacy if not op['cost_known'] and op['status']!='rejected')
    credits=sum(json.loads(op['usage']).get('credits',0) for op in ops)
    units={}
    for kind in {op['kind'] for op in ops}:
        values=[op for op in ops if op['kind']==kind and op['status']!='rejected']
        known=[op['estimated'] for op in values if op['estimated'] is not None]
        units[kind]={'maximum':max(op['reserved'] for op in values) if values else 0,'observed_mean':sum(known)/len(known) if known else None}
    return {'operation_estimates':units,'limit':limit,'estimated_spent':round(float(spent),6),'reserved':round(float(reserved),6),'remaining':max(0,round(float(Decimal(str(limit))-spent-reserved),6)),
            'tavily_credits':credits,'estimated':True,'cost_note':'Databricks costs use matching-model published rates plus a 50% buffer. Tavily credits use pay-as-you-go value; free credits may reduce the cash charge.'}


def increase(connection,document_id,limit):
    if not valid_limit(limit) or limit<=0:raise GenerationError('Enter a positive total research allowance, up to US$1,000.')
    with db.transaction(connection):
        ensure_budget(connection,document_id)
        current=summary(connection,document_id)['limit']
        if limit<current:raise GenerationError('The shared allowance can only be increased; versions and retries do not reset it.')
        if limit!=current:
            connection.execute('UPDATE generator_research_budgets SET limit_usd=?,updated_at=? WHERE document_id=?',(limit,db.now(),document_id))
            connection.execute('INSERT INTO generator_research_budget_log VALUES(?,?,?,?)',(document_id,current,limit,db.now()))
    return summary(connection,document_id)


class Store:
    def __init__(self,connection,job_id):
        self.db=connection;self.job_id=job_id
        row=connection.execute('SELECT document_id,config FROM generator_jobs WHERE id=?',(job_id,)).fetchone()
        self.document_id=row['document_id'];ensure_budget(connection,self.document_id,json.loads(row['config']).get('web_budget_usd',5))
    def budget(self):return summary(self.db,self.document_id)
    def cached(self,identity):
        row=self.db.execute('SELECT value FROM generator_research_cache WHERE document_id=? AND identity=?',(self.document_id,identity)).fetchone()
        return json.loads(row['value']) if row else None
    def save(self,identity,value):
        self.db.execute('INSERT INTO generator_research_cache VALUES(?,?,?) ON CONFLICT(document_id,identity) DO UPDATE SET value=excluded.value',(self.document_id,identity,json.dumps(value,ensure_ascii=False)))
    def operation(self,identity):return self.db.execute('SELECT * FROM generator_research_ops WHERE document_id=? AND identity=?',(self.document_id,identity)).fetchone()
    def reserve(self,identity,kind,maximum):
        if not math.isfinite(maximum) or maximum<=0:raise ResearchPaused('pricing_unavailable','The operation has no trustworthy cost bound.')
        with db.transaction(self.db):
            row=self.operation(identity)
            if row:return row
            uncertain=self.db.execute("SELECT c.stage FROM generator_calls c JOIN generator_jobs j ON j.id=c.job_id WHERE j.document_id=? AND c.status='submitting' AND c.remote_id IS NULL LIMIT 1",(self.document_id,)).fetchone()
            if uncertain:raise ResearchPaused('provider_uncertain','A prior '+uncertain['stage']+' request has an unknown outcome; it will not be repeated.')
            if Decimal(str(maximum))>Decimal(str(self.budget()['remaining'])):raise ResearchPaused('budget_exhausted','The remaining shared research allowance cannot cover the next bounded request.',maximum)
            self.db.execute('INSERT INTO generator_research_ops(document_id,identity,job_id,call_key,kind,status,reserved,created_at) VALUES(?,?,?,?,?,?,?,?)',
                            (self.document_id,identity,self.job_id,identity,kind,'reserved',maximum,db.now()))
            self.db.execute("INSERT INTO generator_calls(job_id,call_key,status,stage,reserved_cost,budget_scope,billing) VALUES(?,?,'reserved',?,?,'research',?)",
                            (self.job_id,identity,kind,maximum,json.dumps({'billing_provider':'databricks' if kind.startswith('research-ai') else 'tavily','research_document_id':self.document_id})))
            return self.operation(identity)
    def begin(self,identity):
        with db.transaction(self.db):
            row=self.operation(identity)
            call=self.db.execute('SELECT status FROM generator_calls WHERE job_id=? AND call_key=?',(self.job_id,identity)).fetchone()
            if not row or row['status']!='reserved' or not call or call['status']!='reserved':
                raise ResearchPaused('provider_uncertain','This reserved request has already been claimed; another submission is not permitted.')
            uncertain=self.db.execute("SELECT c.stage FROM generator_calls c JOIN generator_jobs j ON j.id=c.job_id WHERE j.document_id=? AND c.status='submitting' AND c.remote_id IS NULL AND NOT(c.job_id=? AND c.call_key=?) LIMIT 1",(self.document_id,self.job_id,identity)).fetchone()
            if uncertain:raise ResearchPaused('provider_uncertain','A prior '+uncertain['stage']+' request has an unknown provider outcome.')
            self.db.execute("UPDATE generator_research_ops SET status='submitting' WHERE document_id=? AND identity=?",(self.document_id,identity))
            self.db.execute("UPDATE generator_calls SET status='submitting' WHERE job_id=? AND call_key=?",(self.job_id,identity))
    def complete(self,identity,result,estimated,usage):
        if estimated is not None and (not math.isfinite(estimated) or estimated<0):raise GenerationError('Invalid research usage estimate.')
        self.db.execute("UPDATE generator_research_ops SET status='complete',result=?,estimated=?,usage=? WHERE document_id=? AND identity=?",(json.dumps(result,ensure_ascii=False),estimated,json.dumps(usage),self.document_id,identity))
    def reject(self,identity):
        self.db.execute("UPDATE generator_research_ops SET status='rejected',estimated=0 WHERE document_id=? AND identity=?",(self.document_id,identity))
        self.db.execute("UPDATE generator_calls SET status='rejected' WHERE job_id=? AND call_key=?",(self.job_id,identity))
