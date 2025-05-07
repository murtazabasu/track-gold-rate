import os
from datetime import datetime, timedelta

import msal
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gold_prices.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CLIENT_ID'] = os.getenv('APP_GOLD_PRICE_TRACKER_CLIENT_ID')
app.config['CLIENT_SECRET'] = os.getenv("APP_GOLD_PRICE_TRACKER_CLIENT_SECRET")
app.config['AUTHORITY'] = f"https://login.microsoftonline.com/{os.getenv('SYNVERT_TENANT_ID')}"
app.config['REDIRECT_URI'] = "http://localhost:5000/get_token"
app.config['SCOPES'] = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read"]
db = SQLAlchemy(app)

# MSAL configuration
msal_app = msal.ConfidentialClientApplication(
    app.config['CLIENT_ID'],
    authority=app.config['AUTHORITY'],
    client_credential=app.config['CLIENT_SECRET']
)

class GoldPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_notifications = db.Column(db.Boolean, default=True)
    recipient_email = db.Column(db.String(120))
    last_email_time = db.Column(db.DateTime)

class RefreshToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(1024))

def get_gold_price():
    ounce_gram_factor = 31.1034768
    url_usd_eur = 'https://api.frankfurter.app/latest?from=USD&to=EUR'
    response_usd_eur = requests.get(url_usd_eur).json()
    usd_eur = float(response_usd_eur['rates']['EUR'])
    url_xau_usd = 'https://api.gold-api.com/price/XAU'
    response_xau_usd = requests.get(url_xau_usd).json()
    xau_usd = float(response_xau_usd['price'])
    return (usd_eur * xau_usd) / ounce_gram_factor

def get_access_token():
    refresh_token = RefreshToken.query.first()
    if refresh_token is None:
        return None
    result = msal_app.acquire_token_silent(app.config['SCOPES'], account=None)
    if not result:
        result = msal_app.acquire_token_by_refresh_token(refresh_token.token, scopes=app.config['SCOPES'])
    if "access_token" in result:
        return result["access_token"]
    return None

def send_email(recipient, price):
    access_token = get_access_token()
    if access_token is None:
        print("Error: No access token available. Please authenticate at /login")
        return
    user_endpoint = "https://graph.microsoft.com/v1.0/me"
    user_response = requests.get(user_endpoint, headers={"Authorization": f"Bearer {access_token}"})
    if not user_response.ok:
        print(f"Error retrieving user ID: {user_response.json()}")
        return
    user_id = user_response.json().get("userPrincipalName")
    email_msg = {
        "Message": {
            "Subject": "Gold Price Alert",
            "Body": {
                "ContentType": "Text",
                "Content": f'The gold price is now {price:.2f} € per gram, which is a new low.'
            },
            "ToRecipients": [
                {
                    "EmailAddress": {
                        "Address": recipient
                    }
                }
            ]
        },
        "SaveToSentItems": "true"
    }
    endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/sendMail"
    response = requests.post(endpoint, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json=email_msg)
    if response.ok:
        print("Email sent successfully")
    else:
        print(f"Error sending email: {response.text}")

def fetch_and_store_price():
    with app.app_context():
        try:
            price = get_gold_price()
            today = datetime.utcnow().date()
            today_lowest = db.session.query(db.func.min(GoldPrice.price)).filter(db.func.date(GoldPrice.timestamp) == today).scalar()
            yesterday = today - timedelta(days=1)
            yesterday_lowest = db.session.query(db.func.min(GoldPrice.price)).filter(db.func.date(GoldPrice.timestamp) == yesterday).scalar()
            new_price = GoldPrice(price=price)
            db.session.add(new_price)
            db.session.commit()
            if (today_lowest is None or price < today_lowest): #or (yesterday_lowest is not None and price < yesterday_lowest):
                setting = Setting.query.first()
                if setting and setting.email_notifications:
                    send_email(setting.recipient_email, price)
                    setting.last_email_time = datetime.utcnow()
                    db.session.commit()
        except Exception as e:
            print(f"Error fetching price: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store_price, 'interval', seconds=90)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email_notifications = 'email_notifications' in request.form
        recipient_email = request.form['recipient_email']
        setting = Setting.query.first()
        if setting is None:
            setting = Setting(email_notifications=email_notifications, recipient_email=recipient_email, last_email_time=None)
            db.session.add(setting)
        else:
            setting.email_notifications = email_notifications
            setting.recipient_email = recipient_email
        db.session.commit()
        return redirect(url_for('index'))
    setting = Setting.query.first()
    refresh_token_exists = RefreshToken.query.first() is not None
    return render_template('index.html', setting=setting, is_authenticated=refresh_token_exists, is_logged_in=session.get('logged_in', False))

@app.route('/login')
def login():
    auth_url = msal_app.get_authorization_request_url(
        app.config['SCOPES'],
        redirect_uri=app.config['REDIRECT_URI'],
        state="gold_tracker_auth",
        prompt="consent"
    )
    return redirect(auth_url)

@app.route('/get_token')
def get_token():
    if "code" not in request.args:
        return "Error: No authorization code provided", 400
    result = msal_app.acquire_token_by_authorization_code(
        request.args["code"],
        scopes=app.config['SCOPES'],
        redirect_uri=app.config['REDIRECT_URI']
    )
    if "refresh_token" in result:
        refresh_token = RefreshToken.query.first()
        if refresh_token is None:
            refresh_token = RefreshToken(token=result["refresh_token"])
            db.session.add(refresh_token)
        else:
            refresh_token.token = result["refresh_token"]
        db.session.commit()
        return "Authentication successful. You can close this window."
    return f"Error: {result.get('error_description')}", 400

@app.route('/get_data')
def get_data():
    today = datetime.utcnow().date()
    today_prices = GoldPrice.query.filter(db.func.date(GoldPrice.timestamp) == today).all()
    timestamps = [p.timestamp.isoformat() for p in today_prices]
    prices = [p.price for p in today_prices]
    return jsonify({'timestamps': timestamps, 'prices': prices})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True)