"""Cost gates act before payment; BYOK billing must not appear free."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app
from portal_api import db
from portal_api.generator import DEFAULTS
from portal_api.generation_errors import GenerationError
from portal_api.generation_models import Models
from portal_api.generation_webbudget import web_plan
from portal_api.generation_billing import generation_bill,total_bill,record_bill,usage_bill

CATALOG={'data':[{'id':'openai/gpt-6-luna','context_length':1050000,'pricing':{'prompt':'0.0000001','completion':'0.0000005','input_cache_write':'0.000000125','overrides':[{'prompt':'0.0000002','completion':'0.00000075','input_cache_write':'0.00000025'}]}}]}
ANSWER={'id':'gen-safe-search','choices':[{'message':{'content':'Bounded research notes','annotations':[]},'finish_reason':'stop'}],'usage':{'cost':.001,'is_byok':True,'cost_details':{'upstream_inference_cost':.0005}}}

class WebBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';make_test_app(self.path);self.db=db.connect(self.path);self.id='b'*32
        self.db.execute('INSERT INTO generator_jobs(id,config,status,step,created_at,updated_at) VALUES(?,?,?,?,?,?)',(self.id,json.dumps(DEFAULTS),'running','collect',db.now(),db.now()))
    def tearDown(self):self.db.close();self.temp.cleanup()
    def models(self,**changes):return Models(self.db,self.id,{**DEFAULTS,**changes},lambda text:None)
    def test_full_context_ceiling_fits_thirty_cents(self):
        plan=web_plan(CATALOG,.30);self.assertEqual(plan['reserved_usd'],.291335);self.assertLessEqual(plan['reserved_usd'],.30)
        self.assertEqual(plan['engine'],'parallel');self.assertEqual(plan['mode'],'turbo')
        for budget in (0,.01,.29,1000.01,float('nan')):
            with self.assertRaises(GenerationError):web_plan(CATALOG,budget)
    def test_unverifiable_prices_and_bigger_context_fail_closed(self):
        for change in ({'context_length':2000000},{'pricing':{'prompt':'0.00001','completion':'0.00001'}},{'pricing':{}},{'context_length':None}):
            catalog={'data':[{**CATALOG['data'][0],**change}]}
            with self.assertRaises(GenerationError):web_plan(catalog,.30)
    def test_only_one_non_native_search_is_reserved_and_billed(self):
        models=self.models()
        def provider(method,path,body=None):
            if method=='GET':return CATALOG
            row=self.db.execute('SELECT reserved_cost,budget_scope FROM generator_calls').fetchone()
            self.assertEqual(row['reserved_cost'],.291335);self.assertEqual(row['budget_scope'],'web')
            self.assertEqual(body['plugins'],[{'id':'web','engine':'parallel','mode':'turbo','max_results':5}])
            self.assertEqual(body['tool_choice'],'none');self.assertEqual(body['max_tokens'],1800)
            self.assertEqual(body['service_tier'],'flex');self.assertFalse(body['provider']['allow_fallbacks']);self.assertEqual(body['provider']['only'],['openai/flex'])
            self.assertEqual(body['provider']['max_price'],{'prompt':.25,'completion':.75})
            return ANSWER
        with patch.object(models,'request',side_effect=provider) as call:
            self.assertEqual(models.many('summary',['research'],'web-research',structured=False,web=True)[0]['content'],'Bounded research notes')
            models.many('summary',['different prompt'],'web-research',structured=False,web=True)
            self.assertEqual([item.args[0] for item in call.call_args_list],['GET','POST'])
        row=self.db.execute('SELECT * FROM generator_calls').fetchone();self.assertEqual(row['cost'],.0015);self.assertTrue(row['cost_known'])
    def test_zero_budget_never_calls_provider(self):
        models=self.models(web_budget_usd=0)
        with patch.object(models,'request') as call:
            with self.assertRaises(GenerationError):models.many('summary',['research'],'web-research',structured=False,web=True)
            call.assert_not_called()
    def test_insufficient_budget_makes_no_paid_request(self):
        models=self.models(web_budget_usd=.01)
        with patch.object(models,'request',return_value=CATALOG) as call:
            with self.assertRaises(GenerationError):models.many('summary',['research'],'web-research',structured=False,web=True)
            self.assertEqual([item.args[0] for item in call.call_args_list],['GET'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM generator_calls').fetchone()[0],0)
    def test_uncertain_submission_keeps_reservation_and_never_retries(self):
        models=self.models()
        with patch.object(models,'request',side_effect=[CATALOG,GenerationError('network timeout')]) as call:
            with self.assertRaises(GenerationError):models.many('summary',['research'],'web-research',structured=False,web=True)
            with self.assertRaises(GenerationError):models.many('summary',['research'],'web-research',structured=False,web=True)
            self.assertEqual(call.call_count,2)
        self.assertEqual(self.db.execute('SELECT reserved_cost FROM generator_calls').fetchone()[0],.291335)
    def test_native_search_cannot_reach_transport(self):
        models=self.models()
        with patch('portal_api.generation_models.monitored_call') as call:
            with self.assertRaises(GenerationError):models.request('POST','/chat/completions',{'plugins':[{'id':'web','engine':'native'}]})
            call.assert_not_called()
    def test_byok_and_platform_costs_total_without_double_counting(self):
        self.assertEqual(total_bill({'credit_cost':0,'provider_cost':.701728375,'is_byok':True}),.701728375)
        self.assertAlmostEqual(total_bill({'credit_cost':.001,'provider_cost':.7,'is_byok':True}),.701)
        self.assertEqual(total_bill({'credit_cost':.7,'provider_cost':.6,'is_byok':False}),.7)
        self.assertIsNone(total_bill({'credit_cost':0,'provider_cost':None,'is_byok':True}))
        self.assertIsNone(total_bill({'credit_cost':0,'provider_cost':None,'is_byok':None}))
    def test_missing_provider_details_use_generation_metadata(self):
        models=self.models()
        answer={**ANSWER,'choices':[{'message':{'content':'{"notes":"Evidence"}'},'finish_reason':'stop'}],'usage':{'cost':0}}
        detail={'data':{'id':ANSWER['id'],'total_cost':0,'upstream_inference_cost':.007,'is_byok':True,'service_tier':'flex'}}
        with patch.object(models,'request',side_effect=[answer,detail]) as call:models.many('summary',['notes'],'summarize')
        self.assertEqual([item.args[0] for item in call.call_args_list],['POST','GET'])
        self.assertEqual(self.db.execute('SELECT cost FROM generator_calls').fetchone()[0],.007)
    def test_charges_survive_a_truncated_model_response(self):
        models=self.models();answer={**ANSWER,'choices':[{'message':{'content':'truncated'},'finish_reason':'length'}]}
        with patch.object(models,'request',return_value=answer):
            with self.assertRaises(GenerationError):models.many('summary',['notes'],'summarize')
        row=self.db.execute('SELECT * FROM generator_calls').fetchone();self.assertEqual(row['cost'],.0015);self.assertTrue(row['cost_known'])
        self.assertEqual(json.loads(row['billing'])['generation_id'],ANSWER['id'])
    def test_reconcile_historical_charge_preserves_the_result(self):
        self.db.execute('INSERT INTO generator_calls(job_id,call_key,status,stage,result) VALUES(?,?,?,?,?)',(self.id,'old','complete','web-research:0','[{"content":"original research"}]'))
        bill=generation_bill({'id':'gen-old','total_cost':0,'upstream_inference_cost':.701728375,'is_byok':True,'web_search_engine':'native'})
        record_bill(self.db,self.id,'old',bill)
        row=self.db.execute('SELECT * FROM generator_calls').fetchone();self.assertEqual(row['cost'],.701728375);self.assertIn('original research',row['result'])

if __name__=='__main__':unittest.main()
