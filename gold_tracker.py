from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gold_prices.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['EMAIL_USER'] = os.getenv('EMAIL_USER')
app.config['EMAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')
db = SQLAlchemy(app)

class GoldPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_notifications = db.Column(db.Boolean, default=True)
    recipient_email = db.Column(db.String(120))
    last_email_time = db.Column(db.DateTime)

def get_gold_price():
    ounce_gram_factor = 31.1034768
    url_usd_eur = 'https://api.frankfurter.app/latest?from=USD&to=EUR'
    response_usd_eur = requests.get(url_usd_eur).json()
    usd_eur = float(response_usd_eur['rates']['EUR'])
    url_xau_usd = 'https://api.gold-api.com/price/XAU'
    response_xau_usd = requests.get(url_xau_usd).json()
    xau_usd = float(response_xau_usd['price'])
    return (usd_eur * xau_usd) / ounce_gram_factor

def fetch_and_store_price():
    try:
        price = get_gold_price()
        today = datetime.utcnow().date()
        today_lowest = db.session.query(db.func.min(GoldPrice.price)).filter(db.func.date(GoldPrice.timestamp) == today).scalar()
        yesterday = today - timedelta(days=1)
        yesterday_lowest = db.session.query(db.func.min(GoldPrice.price)).filter(db.func.date(GoldPrice.timestamp) == yesterday).scalar()
        new_price = GoldPrice(price=price)
        db.session.add(new_price)
        db.session.commit()
        if (today_lowest is None or price < today_lowest) or (yesterday_lowest is not None and price < yesterday_lowest):
            setting = Setting.query.first()
            if setting and setting.email_notifications:
                last_email_time = setting.last_email_time
                if last_email_time is None or (datetime.utcnow() - last_email_time) > timedelta(hours=1):
                    send_email(setting.recipient_email, price)
                    setting.last_email_time = datetime.utcnow()
                    db.session.commit()
    except Exception as e:
        print(f"Error fetching price: {e}")

def send_email(recipient, price):
    msg = MIMEText(f'The gold price is now {price:.2f} €, which is a new low.')
    msg['Subject'] = 'Gold Price Alert'
    msg['From'] = app.config['EMAIL_USER']
    msg['To'] = recipient
    with smtplib.SMTP('smtp-mail.outlook.com', 587) as server:
        server.starttls()
        server.login(app.config['EMAIL_USER'], app.config['EMAIL_PASSWORD'])
        server.send_message(msg)

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
    return render_template('index.html', setting=setting)

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