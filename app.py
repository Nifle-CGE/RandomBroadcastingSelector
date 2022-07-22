# Python standard libraries
import datetime
import secrets
import json
import os
import time
import random
import copy
import csv

# Third-party libraries
from flask import Flask, redirect, render_template, url_for, session, request
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from authlib.integrations.flask_client import OAuth
from azure.cosmos import CosmosClient
import jinja2
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import deepl

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
u_cont = db.get_container_client("Web RBS Users")
p_cont = db.get_container_client("Web RBS Posts")

# Mail client setup
sg_client = SendGridAPIClient(config["sendgrid_api_key"])

# OAuth setup
#app.config["SERVER_NAME"] = "rbs.azurewebsites.net"
oauth = OAuth(app)

# Deepl traduction setup
translator = deepl.Translator(config["deepl_auth_key"])

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id, active=True):
    user = User()
    user.import_user(u_cont, user_id)
    if user.id_ == stats["broadcast"]["author"]:
        user.is_broadcaster = True

    if active:
        user.last_active = time.time()
        user.export_user(u_cont)
    return user

# Useful defs
def verify_broadcast():
    if stats["time"]["last_broadcaster"] + 86400 > time.time():
        return "The broadcaster still has time to make his broadcast."
    elif stats["time"]["last_broadcast"] < stats["time"]["last_broadcaster"] and stats["time"]["last_broadcast"] + 86400 > time.time():
        return "The broadcaster has made his broadcast and this posts time isn't over yet."

    with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
        new_post = json.load(sample_file)

    new_post["id"] = stats["broadcast"]["id"]
    new_post["content"] = stats["broadcast"]["content"]
    new_post["author"] = stats["broadcast"]["author"]
    new_post["author_name"] = stats["broadcast"]["author_name"]
    new_post["date"] = stats["broadcast"]["date"]
    new_post["lang"] = stats["broadcast"]["lang"]
    new_post["upvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.upvote = {new_post['id']}", enable_cross_partition_query=True).next()
    new_post["downvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.downvote = {new_post['id']}", enable_cross_partition_query=True).next()
    try:
        new_post["ratio"] = new_post["upvotes"] / new_post["downvotes"]
    except ZeroDivisionError:
        new_post["ratio"] = 1
    p_cont.create_item(new_post)

    stats["broadcast"]["author"] = random.choice(_stuffimporter.pot_brods(u_cont, stats["broadcast"]["author"]))
    stats["broadcast"]["content"] = ""
    stats["broadcasts"]["msgs_sent"] += 1
    try:
        stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] += 1
    except KeyError:
        stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] = 1

    stats["time"]["last_broadcaster"] = time.time()

    code = secrets.token_urlsafe(32)
    stats["codes"]["broadcast"] = code

    _stuffimporter.set_stats(stats)

    brod_obj = load_user(stats["broadcast"]["author"], active=False)
    if not brod_obj.email: return "error : selected user doesn't have an email"

    with open(f"templates/mail.html", "r", encoding="utf-8") as mail_file:
        mail_content = mail_file.read()
    mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net")
    mail_content.replace("{{ brod_code }}", code)

    message = Mail(
        from_email="random.broadcasting.selector@gmail.com",
        to_emails=brod_obj.email,
        subject="RandomBroadcastingSelector : You are the one.",
        html_content=mail_content
    )
    sg_client.send(message)

    return "New broadcaster selected."

def login_or_create_user(id_:str, name:str, email:str, lang:str):
    # Test to see if the user exists in the db
    user = load_user(id_)

    # Doesn't exist? Add it to the database.
    if not user:
        new_user = User(id_=id_, name=name, email=email)
        new_user.export_user(u_cont)
        user = new_user
    elif user.banned: # if user banned send the ban appeal form
        code = secrets.token_urlsafe(32)
        stats["codes"]["ban_appeal"].append(code)
        _stuffimporter.set_stats(stats)
        return render_template(f"{lang}/banned.html", user_id=user.id_, appeal_code=code)

    # Begin user session by logging the user in
    user.is_authenticated = True
    login_user(user)

    # Send user back to homepage
    session["lang"] = lang
    return redirect(url_for("index", lang=lang))

# Routing
@app.route("/")
def index_redirect():
    lang = session.get("lang")
    if not lang:
        lang = "en"

    return redirect(url_for("index", lang=lang))

@app.route("/<lang>/")
def index(lang):
    verify_broadcast()
    try:
        test = render_template(f"{lang}/index.html", stats=stats)
    except jinja2.exceptions.TemplateNotFound:
        return render_template(f"en/message.html", message="This language has not been implemented yet.")

    session["lang"] = lang
    return render_template(f"{lang}/index.html", stats=stats)

# All the login stuff
@app.route("/<lang>/login/")
def login(lang):
    verify_broadcast()
    session["lang"] = lang
    return render_template(f"{lang}/login.html")

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

    if response_json.get("email_verified"):
        unique_id = "gg-" + response_json["sub"]
        users_name = response_json["name"]
        users_email = response_json["email"]
        if response_json["locale"] in LANGUAGE_CODES.keys():
            lang = response_json["locale"]
        else:
            lang = "en"
    else:
        return "User email not available or not verified by Google.", 400

    return login_or_create_user(unique_id, users_name, users_email, lang)

@app.route('/login/twitter/')
def twitter_login():
	# Twitter Oauth Config
	oauth.register(
		name='twitter',
		client_id=config["twitter"]["apiv1_key"],
		client_secret=config["twitter"]["apiv1_secret"],
		api_base_url='https://api.twitter.com/1.1/',
		request_token_url='https://api.twitter.com/oauth/request_token',
		access_token_url='https://api.twitter.com/oauth/access_token',
		authorize_url='https://api.twitter.com/oauth/authorize'
	)
	redirect_uri = url_for('twitter_login_callback', _external=True)
	return oauth.twitter.authorize_redirect(redirect_uri)

@app.route('/login/twitter/callback')
def twitter_login_callback():
    token = oauth.twitter.authorize_access_token()
    resp = oauth.twitter.get("account/verify_credentials.json", params={"include_email": "true", "skip_status": "true"})
    response_json = resp.json()

    if response_json.get("email"):
        unique_id = "tw-" + response_json["id_str"]
        users_name = response_json["name"]
        users_email = response_json.get("email")
        resp = oauth.twitter.get("account/settings.json")
        resp_json = resp.json()
        lang = resp_json.get("language")
        if not lang in LANGUAGE_CODES.keys():
            lang = "en"
    else:
        return "User email not available or not verified by Twitter.", 400

    return login_or_create_user(unique_id, users_name, users_email, lang)

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
        userinfo_endpoint="https://api.github.com/user",
		client_kwargs={'scope': 'user:email'}
	)
	redirect_uri = url_for('github_login_callback', _external=True)
	return oauth.github.authorize_redirect(redirect_uri)

@app.route('/login/github/callback')
def github_login_callback():
    token = oauth.github.authorize_access_token()
    resp = oauth.github.get("user")
    response_json = resp.json()

    if not response_json.get('email'):
        resp = oauth.github.get('user/emails')
        emails = resp.json()
        response_json["email"] = next(email['email'] for email in emails if email['primary'])

    unique_id = "gh-" + str(response_json["id"])
    users_name = response_json["name"]
    users_email = response_json["email"]
    lang = "en"

    return login_or_create_user(unique_id, users_name, users_email, lang)

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
	return redirect(url_for("index", lang=session.get("lang")))
"""

@app.route("/logout")
@login_required
def logout():
    logout_user()
    lang = session.get("lang")
    return redirect(url_for("index", lang=lang))

@app.route("/<lang>/history/<page>")
def history(lang, page):
    verify_broadcast()
    session["lang"] = lang

    post_list = []
    return render_template(f"{lang}/history.html", post_list, hist_page=int(page))

@app.route("/<lang>/post/<id>")
def specific_post(lang, id):
    verify_broadcast()
    session["lang"] = lang

    try:
        post = p_cont.query_items(f"SELECT p FROM Posts p WHERE p.id = {id}", enable_cross_partition_query=True).next()
    except StopIteration:
        return redirect(url_for("not_found", e="This post doesn't exist yet."))
        
    return render_template(f"{lang}/post.html", post=post)

@app.route("/<lang>/statistics/")
def statistics(lang):
    verify_broadcast()
    
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        start_time = time.time()

        stats["broadcast"]["reports"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.report.post_id = {stats['broadcast']['id']} AND NOT u.report.reason = ''", enable_cross_partition_query=True).next()
        stats["broadcast"]["upvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.upvote = {stats['broadcast']['id']}", enable_cross_partition_query=True).next()
        stats["broadcast"]["downvotes"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.downvote = {stats['broadcast']['id']}", enable_cross_partition_query=True).next()

        stats["users"]["num"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 0", enable_cross_partition_query=True).next()
        stats["users"]["banned"] = u_cont.query_items("SELECT VALUE COUNT(1) FROM Users u WHERE u.ban.status = 1", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_hour"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {start_time - 3600}", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_24h"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {start_time - 86400}", enable_cross_partition_query=True).next()
        stats["users"]["lastlog_week"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {start_time - 604800}", enable_cross_partition_query=True).next()
        
        stats["top_posts"]["5_most_upped"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        
        stats["time"]["uptime_str"] = _stuffimporter.seconds_to_str(start_time - stats["time"]["start_time"])
        stats["time"]["stats_last_edited"] = start_time
        stats["time"]["stats_getting"] = time.time() - start_time

        _stuffimporter.set_stats(stats)

    session["lang"] = lang
    return render_template(f"{lang}/stats.html", stats=stats)

@app.route("/stats.json")
def stats_file():
    stats_file = copy.deepcopy(stats)
    stats_file.pop("codes")
    stats_file["broadcast"].pop("author")

    for i in stats["top_posts"]:
        for j in range(len(stats["top_posts"][i])):
            for k in stats["top_posts"][i][j]:
                if k.startswith("_") or k == "author":
                    stats_file["top_posts"][i][j].pop(k)

    return stats_file

@app.route("/<lang>/broadcast/")
@login_required
def broadcast(lang):
    if current_user.id_ != stats["broadcast"]["author"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to be broadcaster to have access to this page.",
        "fr": "Vous devez être diffuseur pour accéder a cette page."}[lang])

    if stats["broadcast"]["content"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already made your broadcast.",
        "fr": "Vous avez déja fait votre diffusion."}[lang])

    session["lang"] = lang
    return render_template(f"{lang}/broadcast.html")

@app.route("/broadcast-callback", methods=["POST"])
def broadcast_callback():
    lang = session.get("lang") if session.get("lang") else "en"
    return request.form
    
    if stats["codes"]["broadcast"] != request.form["brod_code"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to input the code you received in the mail we sent to you.",
        "fr": "Vous devez saisir le code que vous avez reçu dans le mail qui vous a été envoyé."}[lang])
    else:
        stats["codes"]["broadcast"] = ""
    
    if request.form["user_id"] != stats["broadcast"]["author"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "I didn't think it was possible but you did it, so anyway you can only broadcast if you are the broadcaster, which you are not.",
        "fr": "Je pensait pas que c'était possible mais tu l'a fait, bon, de toute façon tu peux pas diffuser si tu  ."}[lang])
    
    with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
        new_post = json.load(sample_file)

    stats["broadcast"]["id"] += 1
    stats["broadcast"]["content"] = request.form["message"]
    stats["broadcast"]["author_name"] = request.form["displayed_name"]
    stats["broadcast"]["date"] = str(datetime.datetime.today().date())

    test = translator.translate_text(request.form["message"], target_lang="EN-US")
    stats["broadcast"]["lang"] = test.detected_source_lang.lower()

    for language in translator.get_target_languages():
        lang_code = language.code
        if len(lang_code) != 2:
            lang_code = lang_code.split("-")[0]
        stats["broadcast"]["trads"][lang_code.lower()] = translator.translate_text(request.form["message"], target_lang=language.code)
    
    stats["time"]["last_broadcast"] = time.time()

    _stuffimporter.set_stats(stats)

    return render_template(f"{lang}/message.html", message=
    {"en": "Your broadcast has been saved.",
    "fr": "Votre diffusion a été enregistrée."}[lang])

@app.route("/ban-appeal-callback", methods=["POST"])
def ban_appeal_callback():
    lang = session.get("lang") if session.get("lang") else "en"
    return request.form

    try:
        stats["codes"]["ban_appeal"].remove(request.form["appeal_code"])
        _stuffimporter.set_stats(stats)
    except ValueError:
        return render_template(f"{lang}/message.html", message=
        {"en": "Get IP banned noob.",
        "fr": "Tu est maintenant ban IP."}[lang])

    user = load_user(request.form["user_id"], active=False)
    if not user.ban_appeal:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already made a ban appeal.",
        "fr": "Vous avez déja fait une demande de débannissement."}[lang])
    user.ban_appeal = request.form["reason"]
    user.export_user(u_cont)

    return render_template(f"{lang}/message.html", message=
    {"en": "Your ban appeal has been saved.",
    "fr": "Votre demande de débannissement a été enregistrée."}[lang])

# Legal stuff
@app.route("/privacy-policy/")
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route("/terms-of-service/")
def terms_of_service():
    return render_template("terms_of_service.html")

@app.route("/<lang>/sitemap/")
def sitemap(lang):
    session["lang"] = lang
    render_template(f"{lang}/sitemap.html")

# Crawling control
@app.route("/robots.txt")
def robots():
    return render_template("robots.html")

# Error handling
@app.errorhandler(404)
def not_found(e):
    lang = session.get('lang')
    if not lang:
        lang = "en"
    return render_template(f"{lang}/not_found.html", e=e), 404

@app.errorhandler(405)
def method_not_allowed(e):
    lang = session.get('lang')
    if not lang:
        lang = "en"
    return render_template(f"{lang}/method_not_allowed.html", e=e), 405

@app.errorhandler(500)
def internal_server_error(e):
    lang = session.get('lang')
    if not lang:
        lang = "en"
    return render_template(f"{lang}/internal_server_error.html", e=e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0")