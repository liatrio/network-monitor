from flask import Flask, render_template, request, session, redirect, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_pymongo import PyMongo    
from util import ping

app = Flask(__name__)
app.secret_key = 'development key'
mongo = PyMongo(app)

#
# User Views/Functions
#

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
            return redirect('/')
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
        return redirect('/')

    return render_template('register.html')

#
# Network Views/Functions
#

@app.route('/register_network', methods=['POST'])
def register_network():
    """Adds a network to the user's list of networks. 
    Returns False if network already exists."""
    hostname = request.form.get('hostname', None)
    print(hostname)
    if not hostname:
        print('bad hostname {}'.format(hostname))
        abort(400)
    if not 'userid' in session:
        print('User not logged in')
        abort(401)
    user = get_user(session['userid'])
    if not user or hostname in user['networks']:
        print('Hostname exists ({} in {})'.format(hostname, user['networks']))
        abort(400)
    mongo.db.users.update_one({'userid': user['userid']}, {'$push': {'networks': hostname}})
    return redirect('/profile')
#
# Other
#

@app.route('/', methods=('GET', 'POST'))
def ping_form():

    error = None
    if request.method == 'POST':
        hostIP = request.form['hostIP']
        try:
            rtt, jitter = ping(hostIP);
        except ValueError as e:
            error = str(e)
        else:
            entry = {'hostIP': {'ip': hostIP,'rtt': rtt,'jitter': jitter}}
            result = mongo.db.hostIPs.insert_one(entry)

    hostIPs = [obj['hostIP'] for obj in mongo.db.hostIPs.find()]
    return render_template('ping.html', hostIPs=hostIPs, error=error)

@app.route('/profile', methods=['GET'])
def profile():
    if 'userid' not in session:
        abort(401) # unauthroized
    user = get_user(session['userid'])
    return render_template('profile.html', user=user)

app.run(host='0.0.0.0', port=8000)

