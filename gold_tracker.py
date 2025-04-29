from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import os
import requests
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gold_prices.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['EMAIL_USER'] = os.getenv('EMAIL_USER')  # xxx.mkb@outlook.com
app.config['EMAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')  # Your password or app password
db = SQLAlchemy(app)

# Database Models
class Price(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    price = db.Column(db.Float)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_notifications = db.Column(db.Boolean, default=True)
    recipient_email = db.Column(db.String(120))
    last_email_time = db.Column(db.DateTime)

# Fetch Gold Price from Alpha Vantage
def get_gold_price():
    api_key = "1YOX3GVJ3A6R7AIQ" #"900GFGTHI3OMVZ4C" #1YOX3GVJ3A6R7AIQ #os.getenv('ALPHA_VANTAGE_API_KEY')
    ounce_gram_factor = 31.1034768
    # Fetch USD/EUR
    # url_usd_eur = f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATErom_currency=USD&to_currency=EUR&apikey={api_key}'
    # response_usd_eur = requests.get(url_usd_eur).json()
    #print(response_usd_eur)
    usd_eur = 0.87777 #float(response_usd_eur['Realtime Currency Exchange Rate']['5. Exchange Rate'])
    # Fetch XAU/USD
    url_xau_usd = f'https://api.gold-api.com/price/XAU'
    response_xau_usd = requests.get(url_xau_usd).json()
    print(response_xau_usd)
    xau_usd = float(response_xau_usd['price'])
    # Calculate XAU/EUR
    xau_eur = usd_eur * xau_usd
    return xau_eur / ounce_gram_factor

# Fetch, Store, and Check Price
def fetch_and_store_price():
    try:
        price = get_gold_price()
        new_price = Price(price=price)
        db.session.add(new_price)
        db.session.commit()
        # Check notification conditions
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        today_lowest = db.session.query(db.func.min(Price.price)).filter(db.func.date(Price.timestamp) == today).scalar()
        yesterday_lowest = db.session.query(db.func.min(Price.price)).filter(db.func.date(Price.timestamp) == yesterday).scalar()
        setting = Setting.query.first()
        if setting and setting.email_notifications:
            if (today_lowest is None or price < today_lowest) or (yesterday_lowest is not None and price < yesterday_lowest):
                last_email_time = setting.last_email_time
                if last_email_time is None or (datetime.utcnow() - last_email_time) > timedelta(hours=1):
                    send_email(setting.recipient_email, price)
                    setting.last_email_time = datetime.utcnow()
                    db.session.commit()
    except Exception as e:
        print(f"Error fetching price: {e}")

# Send Email Alert
def send_email(recipient, price):
    msg = MIMEText(f'The gold price is now {price:.2f} €, which is a new low.')
    msg['Subject'] = 'Gold Price Alert'
    msg['From'] = app.config['EMAIL_USER']
    msg['To'] = recipient
    with smtplib.SMTP('smtp-mail.outlook.com', 587) as server:
        server.starttls()
        server.login(app.config['EMAIL_USER'], app.config['EMAIL_PASSWORD'])
        server.send_message(msg)

# Scheduler Setup
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store_price, 'interval', seconds=90)
scheduler.start()

# Web Interface
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email_notifications = 'email_notifications' in request.form
        recipient_email = request.form['recipient_email']
        setting = Setting.query.first()
        if setting is None:
            setting = Setting(email_notifications=email_notifications, recipient_email=recipient_email)
            db.session.add(setting)
        else:
            setting.email_notifications = email_notifications
            setting.recipient_email = recipient_email
        db.session.commit()
        return redirect(url_for('index'))
    latest_price = Price.query.order_by(Price.timestamp.desc()).first()
    today = datetime.utcnow().date()
    today_prices = Price.query.filter(db.func.date(Price.timestamp) == today).all()
    timestamps = [p.timestamp.isoformat() for p in today_prices]
    prices = [p.price for p in today_prices]
    setting = Setting.query.first()
    return render_template('index.html', 
                           latest_price=latest_price, 
                           setting=setting, 
                           timestamps_json=json.dumps(timestamps), 
                           prices_json=json.dumps(prices))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables
        fetch_and_store_price()  # Initial fetch
    app.run(host='0.0.0.0', port=5000, debug=True)  # Accessible over local network