import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText

# --- Configuration ---
# URL of the Publisher of the Week page
URL = "https://assetstore.unity.com/publisher-sale"

# Email Configuration - Get from GitHub Secrets
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

def scrape_asset_info():
    """Scrapes the Unity Asset Store for the free asset of the week."""
    try:
        response = requests.get(URL)
        response.raise_for_status()  # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, "html.parser")

        # Find the section containing the free asset information
        # Note: These selectors might change if Unity updates their website.
        free_asset_section = soup.find("div", class_=" organismo-destaque")

        if free_asset_section:
            asset_name = free_asset_section.find("h3").get_text(strip=True)
            promo_code = free_asset_section.find("input", {"type": "text"})["value"]
            return asset_name, promo_code
        else:
            return None, None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None, None

def send_email(asset_name, promo_code):
    """Sends an email with the free asset information."""
    subject = "Unity Publisher of the Week - Free Asset!"
    body = f"""
    Hi there!

    This week's free asset from the Unity Asset Store is:

    **Asset:** {asset_name}
    **Promo Code:** {promo_code}

    You can get it here: {URL}

    Enjoy!
    """

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp_server:
            smtp_server.login(SENDER_EMAIL, APP_PASSWORD)
            smtp_server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("Email sent successfully!")
    except smtplib.SMTPException as e:
        print(f"Error sending email: {e}")

if __name__ == "__main__":
    asset, code = scrape_asset_info()
    if asset and code:
        send_email(asset, code)
    else:
        print("Could not find the free asset information.")
