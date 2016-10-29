from flask import Flask, render_template, request, session, redirect, abort, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_pymongo import PyMongo
from util import ping
import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'development key'
mongo = PyMongo(app)

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
        raise ValueError('User does not exist.')
    return check_password_hash(user['pwhash'], password)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        userid = request.form.get('userId', None)
        password = request.form.get('password', None)
        if not all([userid, password]):
            return render_template('login.html', error='Missing field(s).')
        if auth_user(userid, password):
            session['userid'] = userid
            return redirect(session.pop('redirect_url', url_for('profile')))
        else:
            return render_template('login.html', error='Incorrect UserID/Password')

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
        user = create_user(userid, password1)
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

app.run(host='0.0.0.0', port=8000)
