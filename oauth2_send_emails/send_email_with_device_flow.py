import os
import webbrowser

import msal
import requests

client_id = os.getenv("APP_GOLD_PRICE_TRACKER_CLIENT_ID")
tenant_id = os.getenv("SYNVERT_TENANT_ID")
scopes = ["https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/User.Read"]
recipient_email = os.getenv("RECIPIENT_EMAIL")
# Create a public client application
app = msal.PublicClientApplication(
    client_id,
    authority=f"https://login.microsoftonline.com/{tenant_id}"
)

# Initiate device flow - user authentication required
flow = app.initiate_device_flow(scopes=scopes)
if "user_code" not in flow:
    print(flow.get("error"))
    print(flow.get("error_description"))
    exit()

print(flow["message"])

webbrowser.open(flow["verification_uri"])

# get token
result = app.acquire_token_by_device_flow(flow)
if "access_token" in result:
    access_token = result["access_token"]
    print("Access token acquired successfully.")
else:
    print("Failed to acquire access token.")
    print(result.get("error"))
    print(result.get("error_description"))
    exit()

# Email body
email_msg = {
    "Message": {
        "Subject": "Test Email from Python",
        "Body": {
            "ContentType": "Text",
            "Content": "This is a test email sent using Python and Microsoft Graph with Device Code flow."
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

# Get the signed-in user's ID
user_endpoint = "https://graph.microsoft.com/v1.0/me"
user_response = requests.get(user_endpoint, headers={"Authorization": f"Bearer {access_token}"})
print(user_response.json())
user_id = user_response.json().get("userPrincipalName") if user_response.ok else None

if not user_id:
    print("Failed to retrieve user ID.")
    exit()

# Send an email using the Microsoft Graph API
endpoint = f"https://graph.microsoft.com/v1.0/users/{user_id}/sendMail"
headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
response = requests.post(endpoint, headers=headers, json=email_msg)

if response.ok:
    print("Email sent successfully!")
else:
    print("Failed to send email.")
    print(response.text)