# Python standard libraries
import hashlib
import json
import os
import sys
import time
import random
import csv

# Third-party libraries
from flask import Flask, make_response, redirect, render_template, request, url_for
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
login_manager = LoginManager()
login_manager.init_app(app)
# Setting anonymous user
def anon_user_getter():
    anon_user = User()
    anon_user.is_active = False
    anon_user.is_authenticated = False
    anon_user.is_anonymous = True
    return anon_user
login_manager.anonymous_user = anon_user_getter

# Config elements setup
global config, stats
config = _stuffimporter.get_json("config")
stats = _stuffimporter.get_json("stats")
stats["time"]["start_time"] = time.time()
_stuffimporter.set_stats(stats)

with open("langs.csv", "r", encoding="utf-8") as csvfile:
    reader = csv.reader(csvfile)
    LANGUAGE_CODES = {rows[1].lower():rows[0] for rows in reader}

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
#app.config["SERVER_NAME"] = "rbs.azurewebsites.net"
oauth = OAuth(app)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    user = User()
    user.import_user(u_cont, user_id)
    if user.id == stats["broadcast"]["author"]:
        user.is_broadcaster = True
    return user

# Useful defs
def verif_broadcast():
    time_to_next_broadcast = 86400 - (time.time() - stats["time"]["last_broadcast"])
    if time_to_next_broadcast <= 0:
        with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
            new_post = json.load(sample_file)
            new_post["id"] = stats["broadcast"]["broadcaster"]
            new_post["content"] = stats["broadcast"]["content"]
        # TODO : save current message to history

        stats["broadcast"]["broadcaster"] = random.choice(_stuffimporter.pot_brods(u_cont))
        stats["broadcast"]["content"] = ""
        stats["time"]["last_broadcast"] = time.time()

        _stuffimporter.set_stats(stats)

        brod_obj = load_user(stats["broadcast"]["broadcaster"])
        if not brod_obj.email: return

        with open(f"templates/mail.html", "r", encoding="utf-8") as mail_file:
            mail_content = mail_file.read().replace("{{ server_name }}", app.config["SERVER_NAME"])

        message = Mail(
            from_email="random.broadcasting.selector@gmail.com",
            to_emails=brod_obj.email,
            subject="RandomBroadcastingSelector : You are the one.",
            html_content=mail_content
        )
        sg_client.send(message)

# Routing
@app.route("/")
def index_redirect():
    lang = request.cookies.get("lang")
    if not lang:
        lang = "en"

    return redirect(url_for("index", lang=lang))

@app.route("/<lang>/")
def index(lang):
    verif_broadcast()

    resp = make_response(render_template(f"{lang}_index.html", stats=stats))
    resp.set_cookie("lang", lang, max_age=2592000)
    return resp

# All the login stuff
@app.route("/<lang>/login/")
def login(lang):
    verif_broadcast()

    resp = make_response(render_template(f"{lang}_login.html"))
    resp.set_cookie("lang", lang, max_age=2592000)
    return resp

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
        users_name = response_json["name"]
        if response_json["locale"] in LANGUAGE_CODES.keys():
            lang = response_json["locale"]
        else:
            lang = "en"
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
        return render_template(f"{lang}_banned.html", user_id=user.id, id_hashed=hashed_id)

    # Begin user session by logging the user in
    login_user(user)
    user.last_logged_in = time.time()
    user.is_authenticated = True
    user.export_user(u_cont)

    # Send user back to homepage
    resp = make_response(redirect(url_for("index", lang=lang)))
    resp.set_cookie("lang", lang, max_age=2592000)
    return resp

@app.route('/login/twitter/')
def twitter_login():
	# Twitter Oauth Config
	oauth.register(
		name='twitter',
		client_id=config["twitter"]["api_key"],
		client_secret=config["twitter"]["api_secret"],
		api_base_url='https://api.twitter.com/1.1/',
		request_token_url='https://api.twitter.com/oauth/request_token',
		access_token_url='https://api.twitter.com/oauth/access_token',
		authorize_url='https://api.twitter.com/oauth/authenticate'
	)
	redirect_uri = url_for('twitter_login_callback', _external=True)
	return oauth.twitter.authorize_redirect(redirect_uri)

@app.route('/login/twitter/callback')
def twitter_login_callback():
    token = oauth.twitter.authorize_access_token()
    resp = oauth.twitter.get("account/verify_credentials.json", params={"include_email": True, "skip_status": True})
    profile = resp.json()

    return profile
    return redirect(url_for("index", lang=request.cookies.get("lang")))

@app.route('/login/github/')
def github_login():
	# Facebook Oauth Config
	oauth.register(
		name='github',
		client_id=config["github"]["client_id"],
		client_secret=config["github"]["client_secret"],
		api_base_url='https://api.github.com/',
		access_token_url='https://github.com/login/oauth/access_token',
		authorize_url='https://github.com/login/oauth/authorize',
		client_kwargs={'scope': 'user:email'},
        userinfo_endpoint="https://api.github.com/user"
	)
	redirect_uri = url_for('github_login_callback', _external=True)
	return oauth.github.authorize_redirect(redirect_uri)

@app.route('/login/github/callback')
def github_login_callback():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get("/user")
    profile = resp.json()

    return profile
    return redirect(url_for("index", lang=request.cookies.get("lang")))

"""
@app.route('/login/facebook/')
def facebook_login():
	# Facebook Oauth Config
	oauth.register(
		name='facebook',
		client_id=config["facebook"]["client_id"],
		client_secret=config["facebook"]["client_secret"],
		api_base_url='https://graph.facebook.com/',
		access_token_url='https://graph.facebook.com/oauth/access_token',
		authorize_url='https://www.facebook.com/dialog/oauth',
		client_kwargs={'scope': 'email public_profile'},
        userinfo_endpoint="https://graph.facebook.com/me?fields=id,name,email,languages"
	)
	redirect_uri = url_for('facebook_login_callback', _external=True)
	return oauth.facebook.authorize_redirect(redirect_uri)

@app.route('/login/facebook/callback')
def facebook_login_callback():
	token = oauth.facebook.authorize_access_token()
	profile = token["userinfo"]

	return profile
	return redirect(url_for("index", lang=request.cookies.get("lang")))
"""

@app.route("/logout")
@login_required
def logout():
    lang = request.cookies.get("lang")
    logout_user()
    return redirect(url_for("index", lang=lang))

@app.route("/<lang>/history/<page>")
def history(lang, page):
    verif_broadcast()

    resp = make_response(render_template(f"{lang}_history.html", hist_page=page))
    resp.set_cookie("lang", lang, max_age=2592000)
    return resp

@app.route("/<lang>/statistics/")
def statistics(lang):
    verif_broadcast()
    
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        start_time = time.time()

        stats["broadcast"]["reports"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.report.post_id = {stats['broadcast']['post_id']} AND NOT u.report.reason = ''", enable_cross_partition_query=True).next()
        stats["broadcast"]["upvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.upvote = {stats['broadcast']['post_id']}", enable_cross_partition_query=True).next()
        stats["broadcast"]["downvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.downvote = {stats['broadcast']['post_id']}", enable_cross_partition_query=True).next()

        stats["users"]["num"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 0", enable_cross_partition_query=True).next()
        stats["users"]["banned"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 1", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_hour"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_logged_in > {start_time - 3600}", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_24h"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_logged_in > {start_time - 86400}", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_week"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_logged_in > {start_time - 604800}", enable_cross_partition_query=True).next()
        
        stats["top_posts"]["5_most_upped"] = _stuffimporter.itempaged_to_list(u_cont.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = _stuffimporter.itempaged_to_list(u_cont.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = _stuffimporter.itempaged_to_list(u_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = _stuffimporter.itempaged_to_list(u_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        
        stats["time"]["uptime_str"] = _stuffimporter.seconds_to_str(start_time - stats["time"]["start_time"])
        stats["time"]["stats_last_edited"] = start_time
        stats["time"]["stats_getting"] = time.time() - start_time

        _stuffimporter.set_stats(stats)

    resp = make_response(render_template(f"{lang}_stats.html", stats=stats))
    resp.set_cookie("lang", lang, max_age=2592000)
    return resp

@app.route("/ban-appeal-callback", methods=["POST"])
def ban_appeal_register():
    return request.form
    encoded_id = request.form["user_id"].encode("ascii")
    hashed_id = hashlib.sha256("".join([str(encoded_id[i] + app.secret_key[i]) for i in range(len(encoded_id))]).encode("ascii")).hexdigest()
    if hashed_id != request.form["id_hashed"]:
        return "Get IP banned noob", 400

    user = User()

    return "Your ban appeal has been saved."

# Legal stuff
@app.route("/privacy-policy/")
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route("/terms-of-service/")
def terms_of_service():
    return render_template("terms_of_service.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0")