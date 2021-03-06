from requests_oauthlib import OAuth2Session
import json, csv, os, requests, re
from datetime import datetime, timedelta
from time import time
from flask import Flask, request, url_for, redirect, render_template, session, flash, get_flashed_messages, abort
from flask_sslify import SSLify
from config import *
from user import User
from rq import Queue
from worker import conn
from queue_functions import *

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
app.permanent_session_lifetime = timedelta(days=365)
sslify = SSLify(app)
q = Queue(connection=conn)


@app.route("/profile")
def profile():
    print("on /profile {}".format(session))
    if 'logged_in' in session.keys() and session['logged_in'] == True:
        msg = request.args.get('msg')
        u = User(session['user'])
        u.get_by_email(u.email()) # refresh data
        
        session['user'] = u.json() # save any updates to session cookie
        session.modified = True
        return render_template('profile.html', u=u, msg=msg)
    else:
        redirect_response = request.url
        if request.args.get('state') not in ('', None):
            google = OAuth2Session(client_id, scope=scope, redirect_uri=session['redirect_uri'], state=session['state'])
            # Fetch the access token
            token = google.fetch_token(token_url, client_secret=client_secret,
                    authorization_response=redirect_response)
            # Fetch a protected resource, i.e. user profile
            r = google.get('https://www.googleapis.com/oauth2/v1/userinfo')
            data = r.json()
            email, name = data['email'], data['name']
            u = User()
            if u.get_by_email(email) is None:
                print('creating new user')
                if u.create(email, name) == False:
                    print('failed to create new user')
                    abort(500)
            u.set_token(token)
            print('token set')

            session['user'] = u.json()
            session['logged_in'] = True
            session.modified = True
            return redirect('/process')
        else:
            return redirect('/login')

@app.route("/")
def index():
    return render_template('index.html')

@app.route('/undo')
def remove_filter():
    session['remove_filter'] = True
    session.modified == True
    if 'logged_in' in session.keys() and session['logged_in'] == True:
        return redirect('/process')
    else:
        return redirect('/login')

@app.route('/undo_instructions')
def undo_instructions():
    return render_template('undo_instructions.html')

@app.route('/logout/')
@app.route('/logout/<redirect_page>/')
def logout(redirect_page=''):
    redirect_url = '/{}'.format(redirect_page)
    print(redirect_url)
    session['logged_in'] = False
    session.modified = True
    return redirect(redirect_url)

@app.route("/login")
def login():
    print("on /login {}".format(session))
    session['redirect_uri'] = request.url_root.rstrip('/login') + '/profile'
    session.modified = True
    google = OAuth2Session(client_id, scope=scope, redirect_uri=session['redirect_uri'])
    # Redirect user to Google for authorization
    authorization_url, state = google.authorization_url(authorization_base_url,
        # offline for refresh token
        # force to always make user click authorize
        access_type="offline", prompt="select_account")
    session['state'] = state
    session.modified = True
    return redirect(authorization_url)


@app.route('/process')
def process():
    print("on /process {}".format(session))
    if 'logged_in' not in session.keys() or session['logged_in'] != True:
        return redirect('/login')
    u = User(session['user'])
    if 'remove_filter' not in session.keys():
        q.enqueue(make_filters, u.json())
        u.set_filters_made(True)
        msg = '''<p>Thank you!</p>
        <p>So glad we could help you find your voices again.</p>
        '''
        return redirect(url_for('profile', msg=msg))
    else:
        q.enqueue(delete_filters, u.json())
        u.set_filters_made(False)
        msg = '''
        <p>All set, your filter has been removed.</p>
        '''
        session.pop('remove_filter')
        session.modified = True
        return redirect(url_for('profile', msg=msg))

@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/tos')
def tos():
    return render_template('tos.html')


@app.route('/clear')
def clear():
    print("on /clear {}".format(session))
    session.clear()
    session.modified = True
    return redirect('/')


if __name__ == '__main__':
    app.run(ssl_context='adhoc')

