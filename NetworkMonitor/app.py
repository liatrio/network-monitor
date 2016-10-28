from flask import Flask, render_template, request, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from flask_pymongo import PyMongo    
from util import ping
import datetime

app = Flask(__name__)
app.secret_key = 'development key'
mongo = PyMongo(app)

def get_user(userid):
    return mongo.db.users.find_one({'userid': userid})

def create_user(userid, password):
    if get_user(userid):
        raise ValueError('User already exists')
    pwhash = generate_password_hash(password)
    user = {'userid': userid, 'pwhash': pwhash}
    mongo.db.users.insert_one(user)

def auth_user(userid, password):
    user = get_user(userid)
    if not user:
        raise ValueError('User does not exist.')
    return check_password_hash(user['pwhash'], password)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form.get('userId', None)
        password = request.form.get('password', None)
        if not all([user_id, password]):
            return render_template('login.html', error='Missing field(s).')
        if auth_user(user_id, password):
            session['user_id'] = user_id
            return redirect('/')
        else:
            return render_template('login.html', error='Incorrect UserID/Password')

    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return redirect('/')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_id = request.form.get('userId', None)
        password1 = request.form.get('password1', None)
        password2 = request.form.get('password2', None)
        if not all([user_id, password1, password2]):
            return render_template('register.html', error='Missing field(s).')
        if not (3 <= len(user_id) <= 30):
            return render_template('register.html', error='UserID must be between 3 and 32 characters.')
        if not (7 <= len(password1) <= 128):
            return render_template('register.html', error='Password must be between 7 and 128 characters.')
        if get_user(user_id):
            return render_template('register.html', error='User already exists.')
        if password1 != password2:
            return render_template('register.html', error='Passwords do not match.')
        user = create_user(user_id, password1)
        session['user_id'] = user_id
        return redirect('/')

    return render_template('register.html')

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
            entry = {'hostIP': {'ip': hostIP,'rtt': rtt,'jitter': jitter, 'timestamp': datetime.datetime.utcnow()}}
            result = mongo.db.hostIPs.insert_one(entry)

    hostIPs = [obj['hostIP'] for obj in mongo.db.hostIPs.find()]
    return render_template('index.html', hostIPs=hostIPs, error=error)

app.run(host='0.0.0.0', port=8000)

