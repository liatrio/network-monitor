from flask import Flask, render_template, request, session, redirect, abort, flash, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import flask_pymongo
from flask_pymongo import PyMongo
from util import ping
import datetime
from functools import wraps
from sched import scheduler
import eventlet
from celery import Celery


def make_celery(app):
    celery = Celery(app.import_name, backend=app.config['CELERY_BACKEND'],
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

app = Flask(__name__)
app.secret_key = 'development key'
app.config['CELERY_BACKEND'] = 'redis://localhost:6379'
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379'
celery = make_celery(app);
mongo = PyMongo(app)

# Register `ping_all_networks` as a periodic task
celery.conf.CELERYBEAT_SCHEDULE = {
    'ping-all-networks-periodically': {
        'task': 'ping-all-networks',
        'schedule': datetime.timedelta(seconds=3)
    }
}
celery.conf.CELERY_TIMEZONE = 'UTC'

#
# Error Response Functions
#

def error_response(code, message):
    response = jsonify({'message': message})
    response.status_code = code
    return response

#
# User Views/Functions
#

def requires_login(view):
        """Decorator for views that require login. If user is not logged in,
        redirects to login page then redirects back after login"""
        @wraps(view)
        def decorator(*args, **kwargs):
            if 'userid' not in session:
                session['redirect_url'] = request.url
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return decorator

def get_user(userid):
    return mongo.db.users.find_one({'userid': userid})

def create_user(userid, password):
    if get_user(userid):
        raise ValueError('User already exists')
    pwhash = generate_password_hash(password)
    user = {'userid': userid, 'pwhash': pwhash, 'networks': []}
    mongo.db.users.insert_one(user)

def auth_user(userid, password):
    user = get_user(userid)
    if not user:
        raise ValueError('Invalid Username/Password')
    if not check_password_hash(user['pwhash'], password):
        raise ValueError('Invalid Username/Password')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        userid = request.form.get('userId', None)
        password = request.form.get('password', None)
        if not all([userid, password]):
            return render_template('login.html', error='Missing field(s).')
        try:
            auth_user(userid, password)
        except ValueError as e:
            return render_template('login.html', error=str(e))
        else:
            session['userid'] = userid
            return redirect(session.pop('redirect_url', url_for('profile')))

    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('userid', None)
    return redirect('/')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        userid = request.form.get('userId', None)
        password1 = request.form.get('password1', None)
        password2 = request.form.get('password2', None)
        if not all([userid, password1, password2]):
            return render_template('register.html', error='Missing field(s).')
        if not (3 <= len(userid) <= 30):
            return render_template('register.html', error='UserID must be between 3 and 32 characters.')
        if not (7 <= len(password1) <= 128):
            return render_template('register.html', error='Password must be between 7 and 128 characters.')
        if get_user(userid):
            return render_template('register.html', error='User already exists.')
        if password1 != password2:
            return render_template('register.html', error='Passwords do not match.')
        try:
            user = create_user(userid, password1)
        except ValueError as e:
            return render_template('register.html', error=str(e))
        else:
            session['userid'] = userid
        return redirect(session.pop('redirect_url', url_for('profile')))

    return render_template('register.html')

#
# Network Views/Functions
#

@app.route('/register_network', methods=['POST'])
def register_network():
    """Adds a network to the user's list of networks as well as the global
    network list. Returns False if network already exists."""
    hostname = request.form.get('hostname', None)
    if not hostname:
        flash('bad hostname {}'.format(hostname))
        return redirect('/profile')
    if not 'userid' in session:
        flash('User not logged in')
        return redirect('/profile')
    user = get_user(session['userid'])
    if not user or hostname in user['networks']:
        flash('Hostname exists ({} in {})'.format(hostname, user['networks']))
        return redirect('/profile')
    # Ensure that network is reachable
    try:
        ping(hostname)
    except ValueError:
        flash('{} not reachable'.format(hostname))
        return redirect('/profile')
    # Update user networks
    mongo.db.users.update_one({'userid': user['userid']}, {'$push': {'networks': hostname}})
    # Update global network list
    if mongo.db.networks.count({'hostname': hostname}) == 0:
        mongo.db.networks.insert_one({'hostname': hostname})
    return redirect('/profile')

@celery.task(name='ping-all-networks')
def ping_all_networks():
    """Pings all networks and recoreds the data in mongo. Multithreaded to
    increase performance"""

    def get_ping_entry(host):
        try:
            rtt, jitter = ping(host)
        except ValueError:
            entry = {
                'hostname': host,
                'rtt': 0,
                'jitter': 0,
                'failed': True,
                'timestamp': datetime.datetime.utcnow()
            }
        else:
            entry = {
                'hostname': host,
                'rtt': rtt,
                'jitter': jitter,
                'failed': False,
                'timestamp': datetime.datetime.utcnow()
            }
        return entry

    with app.app_context():
        hosts = [obj['hostname'] for obj in mongo.db.networks.find()]
        pool = eventlet.GreenPool()
        for entry in pool.imap(get_ping_entry, hosts):
            mongo.db.pings.insert_one(entry)

#
# API Views
#

@app.route('/get-latest-ping')
def get_latest_ping():
    hostname = request.args.get('hostname', None)
    if not hostname:
        print('Missing paramter "hostname"')
        return error_response(400, 'Missing parameter "hostname".')
    entry = mongo.db.pings.find_one(
        {'hostname': hostname}, sort=[('timestamp', flask_pymongo.DESCENDING)])
    if not entry:
        print('No entries for {} found'.format(hostname))
        return error_response(400, 'No entries for {} found'.format(hostname))
    print(entry)
    return jsonify({
        'hostname': entry['hostname'],
        'rtt': entry['rtt'],
        'jitter': entry['jitter'],
        'failed': entry['failed'],
        'timestamp': entry['timestamp'],
    })

#
# Site Views
#

@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('index.html')

@app.route('/profile', methods=['GET'])
@requires_login
def profile():
    user = get_user(session['userid'])
    return render_template('profile.html', user=user)

@app.route('/dashboard', methods=['GET'])
@requires_login
def dashboard():
    """Shows all of the user's registered network graphs and data"""
    networks = mongo.db.users.find_one({'userid': session['userid']})['networks']
    return render_template('dashboard.html', networks=networks)
