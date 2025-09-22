import os
import re
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
    """Scrapes the Unity Asset Store for the free asset of the week using new selectors."""
    URL = "https://assetstore.unity.com/publisher-sale"
    
    try:
        response = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        selector = "#main > section > div > div > div.relative > div.z-10"
        free_asset_section = soup.select_one(selector)

        if free_asset_section:
            asset_name_element = free_asset_section.find("h2")
            asset_name = asset_name_element.get_text(strip=True) if asset_name_element else "Asset Name Not Found"

            promo_code = None
            description_spans = free_asset_section.find_all("span")
            for span in description_spans:
                span_text = span.get_text()
                # Search for a likely promo code format (e.g., all caps, letters/numbers, 5+ chars long)
                # This regex looks for a whole word consisting of uppercase letters and numbers.
                match = re.search(r'\b[A-Z0-9-]{5,}\b', span_text)
                if match:
                    promo_code = match.group(0)
                    break
            
            return asset_name, promo_code
        else:
            print("Could not find the free asset section using the specified selector.")
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
