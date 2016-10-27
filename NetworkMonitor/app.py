#imports the render_template and request used later
from flask import Flask, render_template, request
from flask_pymongo import PyMongo    #pymongo, hooks us up to the mongodb
from util import ping

app = Flask(__name__)    #the dunder is a weird thing
mongo = PyMongo(app)    #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/<name>')
def hello(name):
    return render_template('name.html',name=name)

items = ['hello', 'there', 'everyone']

@app.route('/suggestions', methods=('GET', 'POST'))
def suggestions():
    if request.method == 'POST':
        suggestion = request.form['suggestion']
        mongo.db.suggestions.insert_one({'suggestion': suggestion})

    suggestions = [obj['suggestion'] for obj in mongo.db.suggestions.find()]

    return render_template('suggestions.html',suggestions=suggestions)

@app.route('/ping', methods=('GET', 'POST'))
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

app.run(host='0.0.0.0', port=8000)
