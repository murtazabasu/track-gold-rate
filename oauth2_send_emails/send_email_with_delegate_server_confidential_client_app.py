"""
The script (send_email_delegate_with_server.py) successfully sends emails
using the Microsoft Graph API with delegate permissions, but it opens a browser 
for token retrieval each time, which is impractical for your gold tracker web application. 
This application, likely built with Flask, needs to send emails in the background 
without user interaction after initial setup. 
Since the organization restricts the "Mail.Send" application permission, the delegate permissions must be used,
which require user consent. 

The solution is to authenticate a service account once to obtain a refresh token,
store it securely, and use it to acquire access tokens silently for email sending.

To avoid repeated browser interactions:
    - Authenticate the user (e.g., a service account) once using the authorization code flow to obtain an access token and a refresh token.
    - Store the refresh token securely in your web application (e.g., in a database).
    - Use the refresh token to acquire new access tokens silently via MSAL's acquire_token_silent or acquire_token_by_refresh_token methods.
    - Use the access token to send emails via the Microsoft Graph API.

This approach requires the service account to authenticate only once, after which the web app can send emails
on their behalf without further user interaction.

Azure AD App Registration Configuration
To support this solution, you need to configure your Azure AD app registration as a confidential 
client (since web apps can securely store a client secret) and ensure it supports delegate permissions.

Access Your App Registration:
    - Sign in to the Azure Portal.
    - Navigate to Azure Active Directory > App registrations > Your application (e.g., "PythonEmailSender").

Set as Web App:
    - Go to Authentication.
    - Ensure the redirect URI http://localhost:5000/get_token is listed under the Web platform 
    (not Mobile and desktop applications, as used previously for the public client).
    - If incorrect, remove the existing URI and add it under Web:
    - Click Add a platform > Web.
    - Enter http://localhost:5000/get_token.
    - Click Configure.
    - Save the changes.

Add a Client Secret:
    - Go to Certificates & secrets.
    - Under Client secrets, click New client secret.
    - Add a description (e.g., "GoldTrackerSecret") and choose an expiration (e.g., 1 year).
    - Click Add.
    - Copy the Value of the secret immediately (not the Secret ID), as it won't be shown again.
    - Note: Store this securely, as it will be used in your Flask app.

Verify API Permissions:
    - Go to API permissions.
    - Ensure Microsoft Graph > Delegated permissions includes:
        - Mail.Send: To send emails.
        - User.Read: To retrieve the user's ID (email address).
    - If missing, add them:
        Click Add a permission > Microsoft Graph > Delegated permissions.
        Select Mail.Send and User.Read.
        Click Add permissions.
    - If required, click Grant admin consent for [your tenant name] to authorize the permissions.

Disable Public Client Flows:
    - Go to Authentication > Advanced settings.
    - Set Allow public client flows to No, as you're now using a confidential client.
    - Save the changes.

Gather Credentials:
    - Note the following from your app registration:
        - Application (client) ID: Your client_id.
        - Directory (tenant) ID: Your tenant_id.
        - Client secret: The secret value you copied.
"""
import os

import msal
import requests
from flask import Flask, redirect, request, session, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management

# Azure AD configuration
CLIENT_ID = os.getenv("APP_GOLD_PRICE_TRACKER_CLIENT_ID")
CLIENT_SECRET = os.getenv("APP_GOLD_PRICE_TRACKER_SECRET_ID")
TENANT_ID = os.getenv("SYNVERT_TENANT_ID")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI = "http://localhost:5000/get_token"  # Adjust to your app's redirect URI
SCOPES = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read"]
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# MSAL configuration
msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET
)

# Simulated secure storage for refresh token (replace with database in production)
REFRESH_TOKEN_STORAGE = {}

@app.route("/login")
def login():
    """Initiate OAuth 2.0 authorization code flow."""
    auth_url = msal_app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        state="gold_tracker_auth"
    )
    return redirect(auth_url)

@app.route("/get_token")
def get_token():
    """Handle redirect and store refresh token."""
    if "code" not in request.args:
        return "Error: No authorization code provided", 400
    result = msal_app.acquire_token_by_authorization_code(
        request.args["code"],
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    if "refresh_token" in result:
        # Store refresh token securely (e.g., in a database)
        REFRESH_TOKEN_STORAGE["service_account"] = result["refresh_token"]
        session["user"] = result.get("id_token_claims", {}).get("oid")
        return "Authentication successful. You can close this window."
    return f"Error: {result.get('error_description')}", 400

@app.route(f"/send_email/{RECIPIENT_EMAIL}")
def send_email(recipient=RECIPIENT_EMAIL):
    """Send an email using a stored refresh token."""
    refresh_token = REFRESH_TOKEN_STORAGE.get("service_account")
    if not refresh_token:
        return redirect(url_for("login"))

    # Acquire token silently using refresh token
    result = msal_app.acquire_token_silent(SCOPES, account=None)
    if not result:
        result = msal_app.acquire_token_by_refresh_token(refresh_token, scopes=SCOPES)

    if "access_token" not in result:
        return f"Error acquiring token: {result.get('error_description')}", 400

    access_token = result["access_token"]

    # Get user ID
    user_endpoint = "https://graph.microsoft.com/v1.0/me"
    user_response = requests.get(
        user_endpoint,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user_id = user_response.json().get("userPrincipalName") if user_response.ok else None

    if not user_id:
        return f"Error retrieving user ID: {user_response.json()}", 400

    # Send email
    email_msg = {
        "Message": {
            "Subject": "Gold Tracker Update",
            "Body": {
                "ContentType": "Text",
                "Content": "This is an automated email from your Gold Tracker app."
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
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=email_msg
    )

    if response.ok:
        return "Email sent successfully!"
    return f"Error sending email: {response.text}", 400

if __name__ == "__main__":
    app.run(debug=True)