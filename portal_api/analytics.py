"""First-party daily analytics. No IP addresses, queries, or referrers are stored."""
from datetime import datetime, timedelta, date as calendar_date
from zoneinfo import ZoneInfo
from hashlib import sha256
import calendar
import hmac
import re
import secrets

from flask import jsonify, request
from . import db

PREFIX = '/bms_integration_hub/api'
ZONE = ZoneInfo('America/Vancouver')


def today():
    return datetime.now(ZONE).date()


def register_analytics(app, conn, login_required, secret):
    # Independent additive tables preserve compatibility with the portal schema.
    with app.app_context():
        with db.transaction(conn()):
            conn().execute('CREATE TABLE IF NOT EXISTS analytics_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn().execute("INSERT OR IGNORE INTO analytics_meta VALUES ('started', ?)", (today().isoformat(),))
            conn().execute("INSERT OR IGNORE INTO analytics_meta VALUES ('top_pages_limit', '8')")
            conn().execute('''CREATE TABLE IF NOT EXISTS analytics_daily (
                day TEXT NOT NULL, path TEXT NOT NULL, visitor TEXT NOT NULL, views INTEGER NOT NULL,
                PRIMARY KEY(day,path,visitor))''')

    @app.post(PREFIX + '/analytics/collect')
    def collect():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Invalid event'), 400
        agent = request.headers.get('User-Agent', '')
        privacy = request.headers.get('DNT') == '1' or request.headers.get('Sec-GPC') == '1'
        bot = not agent or bool(re.search(r'bot|crawler|spider|headless|preview', agent, re.I))
        if set(data) == {'probe'} and data['probe'] is True:
            # Connectivity/privacy diagnosis only: no counter or cookie changes.
            return jsonify(collection_status='privacy_opt_out' if privacy else 'bot_filtered' if bot else 'ready', counted=False)
        if set(data) != {'path'}:
            return jsonify(error='Invalid event'), 400
        path = data['path']
        if not isinstance(path, str) or not re.fullmatch(r'/(?:[a-z0-9-]+\.html)?', path) or path == '/admin.html':
            return jsonify(error='Invalid page'), 400
        if privacy or bot:
            response = app.make_response(('', 204))
            response.headers['X-Analytics-Status'] = 'privacy_opt_out' if privacy else 'bot_filtered'
            return response
        cookie = request.cookies.get('__Secure-nxflo_visitor' if app.config['COOKIE_SECURE'] else 'nxflo_visitor', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', cookie):
            cookie = secrets.token_urlsafe(32)
        day = today()
        visitor = hmac.new(secret, (day.isoformat() + ':' + cookie).encode(), sha256).hexdigest()
        with db.transaction(conn()):
            conn().execute('''INSERT INTO analytics_daily VALUES(?,?,?,1)
                ON CONFLICT(day,path,visitor) DO UPDATE SET views=views+1''', (day.isoformat(), path, visitor))
            conn().execute('DELETE FROM analytics_daily WHERE day < ?', ((day - timedelta(days=400)).isoformat(),))
        response = app.make_response(('', 204))
        response.headers['X-Analytics-Status'] = 'counted'
        response.set_cookie('__Secure-nxflo_visitor' if app.config['COOKIE_SECURE'] else 'nxflo_visitor', cookie,
            max_age=180*86400, secure=app.config['COOKIE_SECURE'], httponly=True, samesite='Lax',
            path=PREFIX + '/analytics/collect')
        return response

    @app.put(PREFIX + '/admin/analytics/preferences')
    @login_required(owner=True)
    def analytics_preferences():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'top_pages_limit'}:
            return jsonify(error='Invalid preferences'), 400
        limit = data['top_pages_limit']
        if type(limit) is not int or not 1 <= limit <= 20:
            return jsonify(error='Choose between 1 and 20 pages'), 400
        with db.transaction(conn()):
            conn().execute("UPDATE analytics_meta SET value=? WHERE key='top_pages_limit'", (str(limit),))
        return jsonify(top_pages_limit=limit)

    @app.get(PREFIX + '/admin/analytics')
    @login_required(owner=True)
    def analytics():
        months = request.args.get('months', '3')
        if months not in ('3', '6'):
            return jsonify(error='Choose 3 or 6 months'), 400
        end = today()
        month_index = end.year * 12 + end.month - 1 - int(months)
        year, month = divmod(month_index, 12)
        start = end.replace(year=year, month=month+1, day=min(end.day, calendar.monthrange(year, month+1)[1]))
        requested_start = start
        started = conn().execute("SELECT value FROM analytics_meta WHERE key='started'").fetchone()[0]
        start = max(start, calendar_date.fromisoformat(started))
        path = request.args.get('path', '')
        pages = [r[0] for r in conn().execute('SELECT DISTINCT path FROM analytics_daily ORDER BY path')]
        if path and path not in pages:
            return jsonify(error='Unknown page'), 400
        rows = {r['day']: dict(r) for r in conn().execute('''SELECT day,count(DISTINCT visitor) visitors,sum(views) page_views
            FROM analytics_daily WHERE day BETWEEN ? AND ? AND (?='' OR path=?) GROUP BY day''',
            (start.isoformat(), end.isoformat(), path, path))}
        daily = []
        cursor = start
        while cursor <= end:
            date = cursor.isoformat()
            daily.append(rows.get(date, {'day': date, 'visitors': 0, 'page_views': 0}))
            cursor += timedelta(days=1)
        limit = int(conn().execute("SELECT value FROM analytics_meta WHERE key='top_pages_limit'").fetchone()[0])
        ranked = conn().execute('''SELECT path,SUM(views) total_views FROM analytics_daily
            WHERE day BETWEEN ? AND ? GROUP BY path ORDER BY total_views DESC,path ASC LIMIT ?''',
            (start.isoformat(),end.isoformat(),limit)).fetchall()
        series_rows = {}
        if ranked:
            marks = ','.join('?' for _ in ranked)
            series_rows = {(row['path'],row['day']):row['views'] for row in conn().execute(
                f'''SELECT path,day,SUM(views) views FROM analytics_daily WHERE day BETWEEN ? AND ?
                    AND path IN ({marks}) GROUP BY path,day''',
                (start.isoformat(),end.isoformat(),*[row['path'] for row in ranked]))}
        top_pages = [dict(path=row['path'],total_views=row['total_views'],daily=[
            dict(day=d['day'],page_views=series_rows.get((row['path'],d['day']),0))
            for d in daily]) for row in ranked]
        return jsonify(top_pages=top_pages,top_pages_limit=limit,
                       daily=daily, pages=pages, started=started, timezone='America/Vancouver',
                       start=start.isoformat(), requested_start=requested_start.isoformat(), end=end.isoformat(), path=path)
