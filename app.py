# Python standard libraries
import hashlib
import json
import os
import sys
import time
import random
import csv

# Third-party libraries
from flask import Flask, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from authlib.integrations.flask_client import OAuth
import requests
from azure.cosmos import CosmosClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Internal imports
import _stuffimporter
from user import User

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# User session management setup
# https://flask-login.readthedocs.io/en/latest
login_manager = LoginManager()
login_manager.init_app(app)

# Config elements setup
global config, stats
config = _stuffimporter.get_json("config")
stats = _stuffimporter.get_json("stats")
stats["time"]["start_time"] = time.time()
_stuffimporter.set_stats(stats)

with open("langs.csv", "r", encoding="utf-8") as csvfile:
    reader = csv.reader(csvfile)
    LANGUAGE_CODES = {rows[1]:rows[0] for rows in reader}

# Database setup
cc = CosmosClient(config["db"]["url"], config["db"]["key"])
db = cc.get_database_client("Main Database")
global u_cont
u_cont = db.get_container_client("Web RBS Users")
global h_cont
h_cont = db.get_container_client("Web RBS History")

# Mail client setup
sg_client = SendGridAPIClient(config["sendgrid_api_key"])

# OAuth setup
app.config["SERVER_NAME"] = "rbs.azurewebsites.net"
oauth = OAuth(app)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.import_user(u_cont, user_id)
    return user

# Useful defs
def get_google_provider_cfg():
    return requests.get(config["google"]["discovery_url"]).json()

def verif_broadcast():
    time_to_next_broadcast = 86400 - (time.time() - stats["broadcast"]["l_b_t"])
    if time_to_next_broadcast <= 0:
        with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
            new_post = json.load(sample_file)
            new_post["id"] = stats["broadcast"]["broadcaster"]
            new_post["content"] = stats["broadcast"]["content"]
        # TODO : save current message to history

        stats["broadcast"]["broadcaster"] = random.choice(_stuffimporter.pot_brods(u_cont))
        stats["broadcast"]["l_b_t"] = time.time()
        stats["broadcast"]["content"] = ""
        
        message = Mail(
            from_email="random.broadcasting.selector@gmail.com",
            to_emails=current_user.email, # TODO : pas bon
            subject="RandomBroadcastingSelector : You are the one.",
            html_content="" # TODO : faire
        )
        sg_client.send(message)

        _stuffimporter.set_stats(stats)

# Routing
@app.route("/")
def index_redirect():
    return redirect(url_for("index", lang="en"))

@app.route("/<lang>/")
def index(lang):
    verif_broadcast()

    return render_template(f"{lang}_main.html")

@app.route("/<lang>/login/")
def login(lang):
    verif_broadcast()

    return render_template(f"{lang}_login.html")

@app.route("/login/google/")
def google_login():
    # Google Oauth Config
	oauth.register(
		name='google',
		client_id=config["google"]["oauth_id"],
		client_secret=config["google"]["oauth_secret"],
		server_metadata_url=config["google"]["discovery_url"],
		client_kwargs={
			'scope': 'openid email profile'
		}
	)
	
	# Redirect to google_login_callback function
	redirect_uri = url_for("google_login_callback", _external=True)
	return oauth.google.authorize_redirect(redirect_uri)

@app.route("/login/google/callback")
def google_login_callback():
    token = oauth.google.authorize_access_token()
    response_json = token["userinfo"]
    return response_json

    if response_json.get("email_verified"):
        unique_id = response_json["sub"]
        users_email = response_json["email"]
        users_name = response_json["given_name"] + " " + response_json["family_name"]
    else:
        return "User email not available or not verified by Google.", 400

    # Test to see if the user exists in the db
    user = User()
    user_exists = user.import_user(u_cont, unique_id)

    # Doesn't exist? Add it to the database.
    if not user_exists:
        new_user = User(id_=unique_id, name=users_name, email=users_email)
        new_user.export_user(u_cont)
        user = new_user
    elif user.banned: # if user banned propose the ban appeal form
        encoded_id = user.id.encode("ascii")
        hashed_id = hashlib.sha256("".join([str(encoded_id[i] + app.secret_key[i]) for i in range(len(encoded_id))]).encode("ascii")).hexdigest()
        return render_template(f"{user.lang}_banned.html", user_id=user.id, id_hashed=hashed_id)

    # Begin user session by logging the user in
    login_user(user)
    user.last_logged_in = time.time()
    user.lang = response_json["locale"]
    user.export_user(u_cont)

    # Send user back to homepage
    return redirect(url_for("index", lang=user.lang))

@app.route('/login/twitter/')
def twitter_login():
	# Twitter Oauth Config
	oauth.register(
		name='twitter',
		client_id=config["twitter"]["api_key"],
		client_secret=config["twitter"]["api_secret"],
		request_token_url='https://api.twitter.com/oauth/request_token',
		request_token_params=None,
		access_token_url='https://api.twitter.com/oauth/access_token',
		access_token_params=None,
		authorize_url='https://api.twitter.com/oauth/authenticate',
		authorize_params=None,
		api_base_url='https://api.twitter.com/1.1/',
		client_kwargs=None,
	)
	redirect_uri = url_for('twitter_login_callback', _external=True)
	return oauth.twitter.authorize_redirect(redirect_uri)

@app.route('/login/twitter/callback')
def twitter_login_callback():
    token = oauth.twitter.authorize_access_token()
    resp = oauth.twitter.get('account/verify_credentials.json')
    profile = resp.json()

    return profile
    return redirect(url_for("index", lang=current_user.lang))

@app.route('/login/facebook/')
def facebook_login():
	# Facebook Oauth Config
	oauth.register(
		name='facebook',
		client_id=config["facebook"]["client_id"],
		client_secret=config["facebook"]["client_secret"],
		access_token_url='https://graph.facebook.com/oauth/access_token',
		access_token_params=None,
		authorize_url='https://www.facebook.com/dialog/oauth',
		authorize_params=None,
		api_base_url='https://graph.facebook.com/',
		client_kwargs={'scope': 'email'},
	)
	redirect_uri = url_for('facebook_login_callback', _external=True)
	return oauth.facebook.authorize_redirect(redirect_uri)

@app.route('/login/facebook/callback')
def facebook_login_callback():
	token = oauth.facebook.authorize_access_token()
	resp = oauth.facebook.get(
		'https://graph.facebook.com/me?fields=id,name,email,picture{url}')
	profile = resp.json()
	return profile
	return redirect(url_for("index", lang=current_user.lang))

@app.route("/logout")
@login_required
def logout():
    lang = current_user.lang
    logout_user()
    return redirect(url_for("index", lang=lang))

@app.route("/<lang>/history/<page>")
def history(lang, page):
    verif_broadcast()

    return render_template(f"{lang}_history.html", hist_page=page)

@app.route("/<lang>/statistics/")
def statistics(lang):
    verif_broadcast()
    
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        start_time = time.time()

        stats["broadcast"]["reports"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.report.timestamp > " + str(stats["bradcast"]["l_b_t"]), enable_cross_partition_query=True).next()
        stats["broadcast"]["upvotes"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.report.timestamp > " + str(stats["bradcast"]["l_b_t"]), enable_cross_partition_query=True).next()
        stats["users"]["num"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 0", enable_cross_partition_query=True).next()
        stats["users"]["banned"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 1", enable_cross_partition_query=True).next()

    # TODO : modifier le système pour utiliser moins de RU en mettant les stats dans config.json et qui s'updatent toutes les heures


    uptime_str = _stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])

    return render_template(f"{lang}_stats.html", stats=stats)

@app.route("/ban-appeal-callback", methods=["POST"])
def ban_appeal_register():
    return request.form
    encoded_id = request.form["user_id"].encode("ascii")
    hashed_id = hashlib.sha256("".join([str(encoded_id[i] + app.secret_key[i]) for i in range(len(encoded_id))]).encode("ascii")).hexdigest()
    if hashed_id != request.form["id_hashed"]:
        return "Get IP banned noob", 400

    return "Your ban appeal has been saved."

@app.route("/licence/")
def licence():
    with open("LICENCE.txt", "r", encoding="utf-8") as licence_file:
        return licence_file.read()

if __name__ == "__main__":
    app.run(host="0.0.0.0")