import os
import requests
import threading
from datetime import datetime
import sys
import os.path
from dotenv import load_dotenv

# Try to load environment variables from multiple possible locations
# First try the current directory
load_dotenv()

# Then try the project root
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'clyne.env')
if os.path.exists(root_env_path):
    load_dotenv(root_env_path)
    print(f"Loaded email config from {root_env_path}")

# Try a few more possible locations
possible_paths = [
    'clyne.env',
    '../clyne.env',
    '../../clyne.env',
    '../../../clyne.env',
]

for path in possible_paths:
    if os.path.exists(path):
        load_dotenv(path)
        print(f"Loaded email config from {path}")
        break

# Email configuration
ZEPTO_AUTH_TOKEN = os.getenv("ZEPTO_AUTH_TOKEN")
ZEPTO_API_URL = os.getenv("ZEPTO_API_URL")
ZEPTO_SENDER_NAME = os.getenv("ZEPTO_SENDER_NAME", "Cryptonel")
ZEPTO_SENDER_EMAIL = os.getenv("ZEPTO_SENDER_EMAIL", "noreply@cryptonel.online")

# Log the email configuration
print(f"Email Configuration: ZEPTO_AUTH_TOKEN: {'Set' if ZEPTO_AUTH_TOKEN else 'Missing'}, ZEPTO_API_URL: {'Set' if ZEPTO_API_URL else 'Missing'}")
print(f"ZEPTO_SENDER_NAME: {ZEPTO_SENDER_NAME}, ZEPTO_SENDER_EMAIL: {ZEPTO_SENDER_EMAIL}")

# If ZEPTO_AUTH_TOKEN is None, try loading directly from env file using manual approach
if not ZEPTO_AUTH_TOKEN:
    try:
        # Try to manually parse the .env file
        with open('clyne.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key_value = line.split('=', 1)
                    if len(key_value) == 2:
                        key, value = key_value
                        if key == 'ZEPTO_AUTH_TOKEN':
                            ZEPTO_AUTH_TOKEN = value
                            print(f"Manually loaded ZEPTO_AUTH_TOKEN from clyne.env")
                        elif key == 'ZEPTO_API_URL':
                            ZEPTO_API_URL = value
                            print(f"Manually loaded ZEPTO_API_URL from clyne.env")
                        elif key == 'ZEPTO_SENDER_NAME':
                            ZEPTO_SENDER_NAME = value
                            print(f"Manually loaded ZEPTO_SENDER_NAME from clyne.env")
                        elif key == 'ZEPTO_SENDER_EMAIL':
                            ZEPTO_SENDER_EMAIL = value
                            print(f"Manually loaded ZEPTO_SENDER_EMAIL from clyne.env")
    except Exception as e:
        print(f"Error manually loading email config: {e}")

# Define constants for our links
DISCORD_LINK = "https://discord.gg/3cVdBNQmGh"
X_LINK = "https://x.com/ClyneBot"

def format_decimal(value):
    """Format a decimal value to 8 decimal places"""
    try:
        return f"{float(value):.8f}"
    except:
        return str(value)

def send_transaction_emails(sender, recipient, transaction, users_collection):
    """
    Send transaction notification emails to both sender and recipient
    """
    try:
        # Get email addresses from users
        sender_email = sender.get("email")
        recipient_email = recipient.get("email")
            
        # Check if valid emails exist
        if not sender_email or not recipient_email:
            print(f"Missing email addresses for notification. Sender: {sender.get('username')}, Recipient: {recipient.get('username')}")
            # Don't proceed if we don't have valid emails
            return False
        
        print(f"Sending transaction notification to sender email: {sender_email}")
        print(f"Sending transaction notification to recipient email: {recipient_email}")
        
        # Format timestamp
        timestamp = transaction.get("timestamp")
        if isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                formatted_time = timestamp
        else:
            formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get transfer reason
        transfer_reason = transaction.get("reason", "Not specified")
        
        # Generate HTML for sender and recipient
        sender_html = generate_sender_email(
            total_amount=transaction.get("amount"),
            tax=transaction.get("tax", transaction.get("fee", "0")),
            recipient_data={'public_address': recipient.get("public_address", "Unknown")},
            transaction_id=transaction.get("tx_id", transaction.get("id", "Unknown")),
            formatted_time=formatted_time,
            reason=transfer_reason
        )
        
        # Use the same amount value for the recipient as the sender to keep information consistent
        recipient_html = generate_recipient_email(
            total_amount=transaction.get("amount"),  # Use the same amount as sender email
            tax=transaction.get("tax", transaction.get("fee", "0")),
            sender_data={'public_address': sender.get("public_address", "Unknown")},
            transaction_id=transaction.get("tx_id", transaction.get("id", "Unknown")),
            formatted_time=formatted_time,
            reason=transfer_reason
        )
        
        # Send emails in separate threads to avoid blocking
        threading.Thread(
            target=send_email,
            args=(
                sender_email, 
                sender.get("username", "Cryptonel User"),
                "CRN Transfer Successful", 
                sender_html
            ),
            daemon=True
        ).start()
        
        threading.Thread(
            target=send_email,
            args=(
                recipient_email, 
                recipient.get("username", "Cryptonel User"),
                "CRN Received Successfully", 
                recipient_html
            ),
            daemon=True
        ).start()
        
        return True
    except Exception as e:
        print(f"Error sending transaction emails: {str(e)}")
        return False

def send_email(to_email, to_name, subject, html_body):
    """Send an email using Zepto API"""
    try:
        # Check if we have required config
        if not all([ZEPTO_AUTH_TOKEN, ZEPTO_API_URL]):
            print(f"Missing Zepto API configuration. Auth Token: {'Set' if ZEPTO_AUTH_TOKEN else 'Missing'}, API URL: {'Set' if ZEPTO_API_URL else 'Missing'}")
            return False
            
        headers = {
            'accept': "application/json",
            'content-type': "application/json",
            'authorization': ZEPTO_AUTH_TOKEN,
        }
        
        payload = {
            "from": {
                "address": ZEPTO_SENDER_EMAIL,
                "name": ZEPTO_SENDER_NAME
            },
            "to": [{
                "email_address": {
                    "address": to_email,
                    "name": to_name
                }
            }],
            "subject": subject,
            "htmlbody": html_body
        }
        
        print(f"Sending email to {to_email}")
        response = requests.post(ZEPTO_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200 or response.status_code == 201:
            print(f"Email sent successfully to {to_email}")
            return True
        else:
            print(f"Failed to send email: Status code {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        import traceback
        print(f"Error traceback: {traceback.format_exc()}")
        return False

def generate_sender_email(total_amount, tax, recipient_data, transaction_id, formatted_time, reason=None):
    """Generate HTML for sender email using user's template"""
    
    # Calculate amount after tax for display
    try:
        amount_after_tax = float(total_amount) - float(tax)
        amount_after_tax_formatted = format_decimal(amount_after_tax)
    except:
        amount_after_tax_formatted = "Error calculating"
    
    # Add reason section if provided
    reason_html = ""
    if reason and reason != "Not specified":
        reason_html = f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px 0; color: #666;">
                Reason:
            </td>
            <td style="padding: 10px 0; text-align: right;">
                {reason}
            </td>
        </tr>
        """
    
    return f"""
    <html>
        <head>
            <title>CRN Transfer Successful</title>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css" rel="stylesheet"/>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #ffffff;
                }}
                .header {{
                    background-color: #1e2329;
                    padding: 20px;
                    text-align: center;
                    color: #f0b90b;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .content {{
                    padding: 20px;
                }}
                .content h1 {{
                    color: #000000;
                    font-size: 24px;
                }}
                .content p {{
                    color: #000000;
                    font-size: 16px;
                }}
                .content .highlight {{
                    font-weight: bold;
                }}
                .content .button {{
                    background-color: #f0b90b;
                    color: #000000;
                    padding: 10px 20px;
                    text-decoration: none;
                    display: inline-block;
                    margin: 20px 0;
                }}
                .content .button:hover {{
                    background-color: #e5a800;
                }}
                .footer {{
                    background-color: #f4f4f4;
                    padding: 20px;
                    text-align: center;
                    border-top: 2px solid #e5e5e5;
                }}
                .footer p {{
                    color: #000000;
                    font-size: 12px;
                }}
                .footer a {{
                    color: #f0b90b;
                    text-decoration: none;
                }}
                .footer .social-icons {{
                    margin: 20px 0;
                }}
                .footer .social-icons a {{
                    margin: 0 10px;
                    color: #000000;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                Cryptonel
            </div>
            <div class="content">
                <h1>CRN Transfer Successful</h1>
                <p style="font-size: 20px; font-weight: bold; margin-bottom: 25px;">
                    You've successfully transferred {format_decimal(total_amount)} CRN, and {amount_after_tax_formatted} CRN was received after fees.
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Total Amount Sent:
                        </td>
                        <td style="padding: 10px 0; text-align: right;">
                            {format_decimal(total_amount)} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Network Fee:
                        </td>
                        <td style="padding: 10px 0; text-align: right;">
                            {format_decimal(tax)} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666; font-weight: bold;">
                            Recipient Receives:
                        </td>
                        <td style="padding: 10px 0; text-align: right; font-weight: bold; color: #4CAF50;">
                            {amount_after_tax_formatted} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Recipient Address:
                        </td>
                        <td style="padding: 10px 0; text-align: right; word-break: break-all;">
                            {recipient_data['public_address']}
                        </td>
                    </tr>
                    {reason_html}
                    <tr>
                        <td style="padding: 10px 0; color: #666;">
                            Transaction ID:
                        </td>
                        <td style="padding: 10px 0; text-align: right; word-break: break-all;">
                            {transaction_id}
                        </td>
                    </tr>
                </table>
                <a class="button" href="{DISCORD_LINK}">
                    Visit Our Discord Server
                </a>
                <p>
                    Don't recognize this activity? Please contact customer support immediately.
                </p>
                <p>
                    Please check with the receiving platform or wallet as the transaction is already confirmed on our Global Transactions Channel on Discord.
                </p>
                <p>
                    This is an automated message, please do not reply.
                </p>
            </div>
            <div class="footer">
                <p>
                    Cryptonel Support
                </p>
                <div class="social-icons">
                    <a href="{DISCORD_LINK}">
                        <i class="fab fa-discord"></i>
                    </a>
                    <a href="{X_LINK}">
                        <i class="fab fa-twitter"></i>
                    </a>
                </div>
                <p>
                    To stay secure, setup Two factor authentication (2FA)
                </p>
                <p>
                    <span class="highlight">
                        Risk warning:
                    </span>
                    Cryptocurrency trading is subject to high market risk.
                </p>
                <p>
                    2025 cryptonel.online, All Rights Reserved
                </p>
            </div>
        </body>
    </html>
    """

def generate_recipient_email(total_amount, tax, sender_data, transaction_id, formatted_time, reason=None):
    """Generate HTML for recipient email using user's template"""
    
    # Calculate amount after tax for display
    try:
        amount_after_tax = float(total_amount) - float(tax)
        amount_after_tax_formatted = format_decimal(amount_after_tax)
    except:
        amount_after_tax_formatted = "Error calculating"
    
    # Add reason section if provided
    reason_html = ""
    if reason and reason != "Not specified":
        reason_html = f"""
        <tr style="border-bottom: 1px solid #eee;">
            <td style="padding: 10px 0; color: #666;">
                Reason:
            </td>
            <td style="padding: 10px 0; text-align: right;">
                {reason}
            </td>
        </tr>
        """
    
    return f"""
    <html>
        <head>
            <title>CRN Received Successfully</title>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.3/css/all.min.css" rel="stylesheet"/>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #ffffff;
                }}
                .header {{
                    background-color: #1e2329;
                    padding: 20px;
                    text-align: center;
                    color: #f0b90b;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .content {{
                    padding: 20px;
                }}
                .content h1 {{
                    color: #000000;
                    font-size: 24px;
                }}
                .content p {{
                    color: #000000;
                    font-size: 16px;
                }}
                .content .highlight {{
                    font-weight: bold;
                }}
                .content .button {{
                    background-color: #f0b90b;
                    color: #000000;
                    padding: 10px 20px;
                    text-decoration: none;
                    display: inline-block;
                    margin: 20px 0;
                }}
                .content .button:hover {{
                    background-color: #e5a800;
                }}
                .footer {{
                    background-color: #f4f4f4;
                    padding: 20px;
                    text-align: center;
                    border-top: 2px solid #e5e5e5;
                }}
                .footer p {{
                    color: #000000;
                    font-size: 12px;
                }}
                .footer a {{
                    color: #f0b90b;
                    text-decoration: none;
                }}
                .footer .social-icons {{
                    margin: 20px 0;
                }}
                .footer .social-icons a {{
                    margin: 0 10px;
                    color: #000000;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                Cryptonel
            </div>
            <div class="content">
                <h1>CRN Received Successfully</h1>
                <p style="font-size: 20px; font-weight: bold; margin-bottom: 25px;">
                    You've received {amount_after_tax_formatted} CRN after network fees.
                </p>
                <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Transaction Amount:
                        </td>
                        <td style="padding: 10px 0; text-align: right;">
                            {format_decimal(total_amount)} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Network Fee:
                        </td>
                        <td style="padding: 10px 0; text-align: right;">
                            {format_decimal(tax)} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666; font-weight: bold;">
                            Net Amount Received:
                        </td>
                        <td style="padding: 10px 0; text-align: right; font-weight: bold; color: #4CAF50;">
                            {amount_after_tax_formatted} CRN
                        </td>
                    </tr>
                    <tr style="border-bottom: 1px solid #eee;">
                        <td style="padding: 10px 0; color: #666;">
                            Public Address:
                        </td>
                        <td style="padding: 10px 0; text-align: right; word-break: break-all;">
                            {sender_data['public_address']}
                        </td>
                    </tr>
                    {reason_html}
                    <tr>
                        <td style="padding: 10px 0; color: #666;">
                            Transaction ID:
                        </td>
                        <td style="padding: 10px 0; text-align: right; word-break: break-all;">
                            {transaction_id}
                        </td>
                    </tr>
                </table>
                <a class="button" href="{DISCORD_LINK}">
                    Visit Our Discord Server
                </a>
                <p>
                    Don't recognize this activity? Please contact customer support immediately.
                </p>
                <p>
                    Please check with the receiving platform or wallet as the transaction is already confirmed on our Global Transactions Channel on Discord.
                </p>
                <p>
                    This is an automated message, please do not reply.
                </p>
            </div>
            <div class="footer">
                <p>
                    Cryptonel Transaction
                </p>
                <div class="social-icons">
                    <a href="{DISCORD_LINK}">
                        <i class="fab fa-discord"></i>
                    </a>
                    <a href="{X_LINK}">
                        <i class="fab fa-twitter"></i>
                    </a>
                </div>
                <p>
                    To stay secure, setup 2FA
                </p>
                <p>
                    <span class="highlight">
                        Risk warning:
                    </span>
                    Cryptocurrency trading is subject to high market risk.
                </p>
                <p>
                    2025 cryptonel.online, All Rights Reserved
                </p>
            </div>
        </body>
    </html>
    """ 