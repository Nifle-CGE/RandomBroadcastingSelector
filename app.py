# Python standard libraries
import hashlib
import json
import os
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
from oauthlib.oauth2 import WebApplicationClient
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

# OAuth 2 client setup
client = WebApplicationClient(config["google"]["oauth_id"])

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
            to_emails=current_user.email,
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

@app.route("/<lang>/login")
def login(lang):
    verif_broadcast()

    return render_template(f"{lang}_login.html")

@app.route("/login/google")
def google_login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Use library to construct the request for Google login and provide
    # scopes that let you retrieve user's profile from Google
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route("/login/google/callback")
def google_login_callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")
    # Find out what URL to hit to get tokens that allow you to ask for
    # things on behalf of a user
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]
    # Prepare and send a request to get tokens! Yay tokens!
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(config["google"]["oauth_id"], config["google"]["oauth_secret"]),
    )

    # Parse the tokens!
    client.parse_request_body_response(json.dumps(token_response.json()))

    # Now that you have tokens (yay) let's find and hit the URL
    # from Google that gives you the user's profile information,
    # including their Google profile image and email
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    # You want to make sure their email is verified.
    # The user authenticated with Google, authorized your
    # app, and now you've verified their email through Google!
    response_json = userinfo_response.json()
    if response_json.get("email_verified"):
        unique_id = response_json["sub"]
        users_email = response_json["email"]
        users_name = response_json["given_name"]
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
    user.export_user(u_cont)

    # Send user back to homepage
    return redirect(url_for("index", lang=user.lang))

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
        stats["users"]["num"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 0", enable_cross_partition_query=True).next()
        stats["users"]["banned"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 1", enable_cross_partition_query=True).next()

    # TODO : modifier le système pour utiliser moins de RU en mettant les stats dans config.json et qui s'updatent toutes les heures


    uptime_str = _stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])

    return render_template(f"{lang}_stats.html", stats=stats)

@app.route("/ban-appeal-callback", methods=["POST"])
def ban_appeal_register():
    print(request.form)
    encoded_id = request.form["user_id"].encode("ascii")
    hashed_id = hashlib.sha256("".join([str(encoded_id[i] + app.secret_key[i]) for i in range(len(encoded_id))]).encode("ascii")).hexdigest()
    if hashed_id != request.form["id_hashed"]:
        return "Get IP banned noob", 400

    return "Your ban appeal has been saved."    

if __name__ == "__main__":
    app.run(debug=True, ssl_context="adhoc")