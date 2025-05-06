# with credentials client flow - no user signin required - uses Delegate Permission for Send.Mail
import os
import threading
import time
import webbrowser

import msal
import requests
from flask import Flask, request

client_id = os.getenv("APP_GOLD_PRICE_TRACKER_CLIENT_ID")
tenant_id = os.getenv("SYNVERT_TENANT_ID")
scopes = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read"]
redirect_uri = "http://localhost:5000/getToken"
recipient_email = "murtazakmb@outlook.com"

# Create a public client application
# If the redirect URI is configured under the Web platform in the app registration, it will not be compatible
# with PublicClientApplication as Web platform is intended for confidential clients only and thereforem it needs `client_secret`.
# Public clients, such as those using msal.PublicClientApplication,require redirect URIs under the Mobile and desktop applications platform (Redirect URI best practices).
# This misconfiguration causes Azure AD to expect a client secret, as Web platform apps are assumed to be confidential.
app = msal.PublicClientApplication(
    client_id,
    authority=f"https://login.microsoftonline.com/{tenant_id}"
)

# Set up Flask server to handle redirect
flask_app = Flask(__name__)
auth_code = None

@flask_app.route('/getToken') #getToken
def get_token():
    global auth_code
    auth_code = request.args.get('code')
    return "Token received, you can close this window."

def run_flask():
    flask_app.run(port=5000)

# Start Flask server in a separate thread
threading.Thread(target=run_flask, daemon=True).start()

# Get the authorization URL
auth_url = app.get_authorization_request_url(scopes=scopes, state="some_state", redirect_uri=redirect_uri)
print(f"Please go to: {auth_url}")
webbrowser.open(auth_url)

# Wait for the authorization code
print("Waiting for authorization code...")
while auth_code is None:
    time.sleep(1)

# Exchange the authorization code for tokens
result = app.acquire_token_by_authorization_code(
    auth_code,
    scopes=scopes,
    redirect_uri=redirect_uri
)

if "access_token" in result:
    access_token = result["access_token"]
    print("Access token acquired successfully.")
else:
    print("Failed to acquire access token.")
    print(result.get("error"))
    print(result.get("error_description"))
    exit()

# Send an email using the Microsoft Graph API
email_msg = {
    "Message": {
        "Subject": "Test Email from Python",
        "Body": {
            "ContentType": "Text",
            "Content": "This is a test email sent using Python and Microsoft Graph with Delegate permissions."
        },
        "ToRecipients": [
            {
                "EmailAddress": {
                    "Address": f"{recipient_email}"
                }
            }
        ]
    },
    "SaveToSentItems": "true"
}

# Get the signed-in user's ID (email address) from the token
user_endpoint = "https://graph.microsoft.com/v1.0/me"
user_response = requests.get(user_endpoint, headers={"Authorization": f"Bearer {access_token}"})
user_id = user_response.json().get("userPrincipalName") if user_response.ok else None

if not user_id:
    print("Failed to retrieve user ID.")
    exit()

endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/sendMail"
headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
response = requests.post(endpoint, headers=headers, json=email_msg)

if response.ok:
    print("Email sent successfully!")
else:
    print("Failed to send email.")
    print(response.text)