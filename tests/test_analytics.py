"""Authorization, daily visitor grain, coverage, exclusions and persistence."""
from datetime import date
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_portal_auth import make_test_app, sign_in, ORIGIN
from portal_api import PREFIX, db


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / 'db.sqlite3'
        self.day = patch('portal_api.analytics.today', return_value=date(2026, 10, 28))
        self.day.start()
        self.app = make_test_app(self.path)
        self.client = self.app.test_client()
        self.owner = self.app.test_client()
        sign_in(self.owner)

    def tearDown(self):
        self.day.stop()
        self.temp.cleanup()

    def collect(self, client=None, path='/', agent='Mozilla/5.0'):
        return (client or self.client).post(PREFIX+'/analytics/collect', json={'path':path},
            headers={'Origin':ORIGIN, 'User-Agent':agent})

    def report(self, client=None, query=''):
        return (client or self.owner).get(PREFIX+'/admin/analytics'+query)

    def test_anonymous_and_non_owner_cannot_read(self):
        self.assertEqual(self.report(self.client).status_code,401)
        sign_in(self.client, 'member','member@example.com')
        self.assertEqual(self.report(self.client).status_code,403)

    def test_distinct_browsers_across_pages_and_repeat_views(self):
        for path in ('/','/','/about.html'): self.assertEqual(self.collect(path=path).status_code,204)
        self.collect(self.app.test_client())
        report = self.report().json
        self.assertEqual(report['daily'][-1],dict(day='2026-10-28',visitors=2,page_views=4))
        self.assertEqual(len(report['daily']),1)
        self.assertEqual(report['start'],'2026-10-28')
        self.assertEqual(self.report(query='?path=/about.html').json['daily'][-1]['page_views'],1)
        self.assertEqual(self.report(query='?months=6').json['start'],'2026-10-28')
        self.assertEqual(self.report(query='?months=6').json['requested_start'],'2026-04-28')
        self.assertEqual(self.report(query='?months=0').status_code,400)
        self.assertEqual(self.report(query='?path=/missing.html').status_code,400)

    def test_owner_public_visits_count_immediately_after_sign_in(self):
        self.assertEqual(self.collect(self.owner).status_code, 204)
        self.assertEqual(self.collect(self.owner, path='/about.html').status_code, 204)
        self.assertEqual(self.collect(self.owner).status_code, 204)
        today = self.report().json['daily'][-1]
        self.assertEqual(today['visitors'], 1)
        self.assertEqual(today['page_views'], 3)
        self.assertEqual(self.report(query='?path=/about.html').json['daily'][-1]['page_views'], 1)
        self.assertEqual(self.collect(self.owner, path='/admin.html').status_code, 400)
        self.assertEqual(self.report().json['daily'][-1]['page_views'], 3)

    def test_privacy_headers_still_exclude_owner_and_anonymous(self):
        for client in (self.owner, self.client):
            for header in ('DNT', 'Sec-GPC'):
                response = client.post(PREFIX+'/analytics/collect', json={'path':'/'},
                    headers={'Origin':ORIGIN, 'User-Agent':'Mozilla/5.0', header:'1'})
                self.assertEqual(response.status_code, 204)
        self.assertEqual(self.report().json['daily'][-1]['page_views'], 0)

    def test_exclusions_validation_and_origin(self):
        self.collect(agent='Googlebot')
        self.assertEqual(self.report().json['daily'][-1]['page_views'],0)
        for path in ('/admin.html','/?email=secret','https://evil.test/','/bms_integration_hub/'):
            self.assertEqual(self.collect(path=path).status_code,400)
        self.assertEqual(self.client.post(PREFIX+'/analytics/collect',json={'path':'/'}).status_code,403)
        self.assertEqual(self.client.post(PREFIX+'/analytics/collect',json=['/'],headers={'Origin':ORIGIN}).status_code,400)

    def test_cookie_persistence_and_zero_days(self):
        self.collect()
        with patch('portal_api.analytics.today', return_value=date(2026,10,30)):
            report=self.report().json
            self.assertEqual(report['daily'][-1]['visitors'],0)
            self.collect()
            self.assertEqual(self.report().json['daily'][-1]['visitors'],1)
        restarted=make_test_app(self.path)
        owner=restarted.test_client();sign_in(owner)
        self.assertEqual(self.report(owner).json['daily'][-1]['page_views'],1)
        with db.connect(self.path) as conn:
            rows=conn.execute('SELECT * FROM analytics_daily ORDER BY day').fetchall()
            self.assertNotEqual(rows[0]['visitor'],rows[1]['visitor'])

    def test_collection_probe_explains_exclusions_without_counting_or_cookie(self):
        for headers, expected in (({}, 'ready'), ({'DNT':'1'}, 'privacy_opt_out'),
                                  ({'Sec-GPC':'1'}, 'privacy_opt_out'), ({'User-Agent':'Googlebot'}, 'bot_filtered')):
            response = self.client.post(PREFIX+'/analytics/collect', json={'probe':True},
                headers={'Origin':ORIGIN,'User-Agent':'Mozilla/5.0',**headers})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json,{'collection_status':expected,'counted':False})
            self.assertNotIn('Set-Cookie',response.headers)
        self.assertEqual(self.report().json['daily'][-1]['page_views'],0)

    def test_top_page_ranking_and_daily_series(self):
        with db.connect(self.path) as conn:
            conn.execute("UPDATE analytics_meta SET value='2026-10-27' WHERE key='started'")
            conn.executemany('INSERT INTO analytics_daily VALUES(?,?,?,?)', [
                ('2026-10-28',f'/page-{i:02}.html','fixture',20-i) for i in range(10)])
            conn.execute("INSERT INTO analytics_daily VALUES('2026-10-27','/page-01.html','fixture',3)")
            conn.execute("INSERT INTO analytics_daily VALUES('2025-01-01','/old.html','fixture',9999)")
        result=self.report().json
        self.assertEqual(result['top_pages_limit'],8)
        self.assertEqual(len(result['top_pages']),8)
        self.assertEqual(result['top_pages'][0]['path'],'/page-01.html')
        self.assertEqual(result['top_pages'][0]['total_views'],22)
        self.assertEqual(result['start'],'2026-10-27')
        self.assertEqual(len(result['daily']),2)
        self.assertEqual(result['top_pages'][0]['daily'][0]['page_views'],3)
        second=result['top_pages'][1]
        self.assertEqual(second['path'],'/page-00.html')
        self.assertEqual(second['daily'][-2]['page_views'],0)
        self.assertEqual(second['daily'][-1]['page_views'],20)
        for series in result['top_pages']:
            self.assertEqual(series['total_views'],sum(r['page_views'] or 0 for r in series['daily']))
            self.assertEqual([r['day'] for r in series['daily']],[r['day'] for r in result['daily']])
        csrf=self.owner.get(PREFIX+'/me').json['csrf_token']
        self.owner.put(PREFIX+'/admin/analytics/preferences',json={'top_pages_limit':2},headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
        self.assertEqual([s['path'] for s in self.report().json['top_pages']],['/page-01.html','/page-00.html'])

    def test_page_limit_is_validated_owner_only_and_persistent(self):
        route=PREFIX+'/admin/analytics/preferences'
        self.assertEqual(self.app.test_client().put(route,json={'top_pages_limit':5},headers={'Origin':ORIGIN}).status_code,401)
        self.assertEqual(self.owner.put(route,json={'top_pages_limit':5},headers={'Origin':ORIGIN}).status_code,403)
        token=self.owner.get(PREFIX+'/me').json['csrf_token']
        headers={'Origin':ORIGIN,'X-CSRF-Token':token}
        for value in (0,21,True,8.0,'8'):
            self.assertEqual(self.owner.put(route,json={'top_pages_limit':value},headers=headers).status_code,400)
        self.assertEqual(self.owner.put(route,json={'top_pages_limit':5},headers=headers).status_code,200)
        self.assertEqual(self.report().json['top_pages_limit'],5)
        restarted=make_test_app(self.path);owner=restarted.test_client();sign_in(owner)
        self.assertEqual(self.report(owner).json['top_pages_limit'],5)
        sign_in(self.client,'member','member@example.com')
        member_token=self.client.get(PREFIX+'/me').json['csrf_token']
        self.assertEqual(self.client.put(route,json={'top_pages_limit':3},headers={'Origin':ORIGIN,'X-CSRF-Token':member_token}).status_code,403)

    def test_admin_width_is_validated_persistent_and_account_specific(self):
        route = PREFIX + '/admin/preferences'
        self.assertEqual(self.client.get(route).status_code, 401)
        self.assertEqual(self.owner.get(route).json, {'browser_width': False})
        token = self.owner.get(PREFIX+'/me').json['csrf_token']
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': token}
        self.assertEqual(self.owner.put(route, json={'browser_width': True}, headers={'Origin': ORIGIN}).status_code, 403)
        for payload in ({}, {'browser_width': 1}, {'browser_width': 'true'}, {'browser_width': None}, {'browser_width': True, 'user_id': 2}):
            self.assertEqual(self.owner.put(route, json=payload, headers=headers).status_code, 400)
        self.assertEqual(self.owner.put(route, json={'browser_width': True}, headers=headers).status_code, 200)
        restarted = make_test_app(self.path).test_client()
        sign_in(restarted)
        self.assertEqual(restarted.get(route).json, {'browser_width': True})
        sign_in(self.client, 'member', 'member@example.com')
        with db.connect(self.path) as connection:
            role = connection.execute('SELECT id FROM roles LIMIT 1').fetchone()['id']
            connection.execute("UPDATE users SET status='approved', role_id=? WHERE google_subject='member'", (role,))
        self.assertEqual(self.client.get(route).json, {'browser_width': False})
        member_headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.client.get(PREFIX+'/me').json['csrf_token']}
        self.client.put(route, json={'browser_width': False}, headers=member_headers)
        self.assertEqual(self.owner.get(route).json, {'browser_width': True})
        self.owner.put(route, json={'browser_width': False}, headers=headers)
        self.assertEqual(self.owner.get(route).json, {'browser_width': False})

    def test_history_grows_from_collection_start_and_then_rolls(self):
        self.collect()
        with patch('portal_api.analytics.today',return_value=date(2026,10,29)):
            result=self.report().json
            self.assertEqual([r['day'] for r in result['daily']],['2026-10-28','2026-10-29'])
            self.assertEqual(result['daily'][-1]['page_views'],0)
            self.assertEqual(result['top_pages'][0]['daily'][-1]['page_views'],0)
        with db.connect(self.path) as conn:
            conn.execute("INSERT INTO analytics_daily VALUES('2027-02-01','/about.html','fixture',3)")
        with patch('portal_api.analytics.today',return_value=date(2027,5,28)):
            three=self.report(query='?months=3').json
            six=self.report(query='?months=6').json
            self.assertEqual(three['start'],'2027-02-28')
            self.assertEqual(six['start'],'2026-11-28')
            self.assertEqual(sum(r['page_views'] for r in three['daily']),0)
            self.assertEqual(sum(r['page_views'] for r in six['daily']),3)
            self.assertTrue(all(r['visitors'] is not None for r in six['daily']))

    def test_expired_session_cannot_read(self):
        with db.connect(self.path) as conn: conn.execute("UPDATE sessions SET expires_at='2000-01-01'")
        self.assertEqual(self.report().status_code,401)

if __name__=='__main__': unittest.main()
