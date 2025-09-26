import os
import re
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, time, timezone

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

        selector = "[data-type='CalloutSlim']"
        free_asset_section = soup.select_one(selector)

        if free_asset_section:
            asset_name_element = free_asset_section.find("h2")
            asset_name = asset_name_element.get_text(strip=True) if asset_name_element else "Asset Name Not Found"

            asset_image_element = free_asset_section.find("img")
            asset_image = asset_image_element.get("src") if asset_image_element else ""

            asset_button_element = free_asset_section.find("a")
            asset_url = asset_button_element.get("href") if asset_button_element else ""

            asset_description_element = free_asset_section.find(class_="body")
            asset_description = asset_description_element.get_text(strip=True) if asset_description_element else "Asset Description Not Found"
            
            return asset_name, asset_image, asset_description, asset_url
        else:
            print("Could not find the free asset section using the specified selector.")
            return None, None, None, None
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None, None, None, None

def next_weekday_at_time(weekday: int, target_time: time, tz=timezone.utc):
    now = datetime.now(tz)
    days_ahead = (weekday - now.weekday() + 7) % 7
    if days_ahead == 0 and now.time() >= target_time:
        days_ahead = 7

    next_day = (now + timedelta(days=days_ahead)).date()
    return datetime.combine(next_day, target_time, tzinfo=tz)

def get_expiry_date():
    # Get next Thursday at 15:00 UTC
    next_thursday_3pm_utc = next_weekday_at_time(weekday=3, target_time=time(15, 0))
    # Format it like: October 2, 2025 at 3:00PM UTC
    return next_thursday_3pm_utc.strftime("%B %-d, %Y at %-I:%M%p UTC")

def send_email(asset_name, asset_image, asset_description, asset_url):
    """Sends an email with the free asset information."""
    expiry_date_formatted = get_expiry_date()
    subject = "Unity Publisher of the Week - Free Asset!"
    body = f"""
    <html>
    <body style="margin:0; padding:1rem; background-color:#ffffff; font-family:Helvetica, Arial, sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px; margin:0 auto; border-collapse:collapse;">
        
        <!-- Image -->
        <tr>
          <td style="padding:0;">
            <img src="{asset_image}" alt="Asset Image" width="600" style="display:block; width:100%; max-width:600px; height:auto; border-radius:12px 12px 0 0;">
          </td>
        </tr>

        <!-- Content -->
        <tr>
          <td bgcolor="#000000" style="padding:32px; color:#ffffff; border-radius:0 0 12px 12px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-size:14px; font-weight:600; text-transform:uppercase; letter-spacing:0.18em; padding-bottom:20px;">
                  Free asset of the week
                </td>
              </tr>
              <tr>
                <td style="font-size:34px; line-height:38px; font-weight:700; letter-spacing:-0.006em; padding-bottom:20px;">
                  {asset_name}
                </td>
              </tr>
              <tr>
                <td style="font-size:18px; line-height:26px; letter-spacing:-0.006em; padding-bottom:30px;">
                  {asset_description}
                </td>
              </tr>
              <tr>
                <td align="left">
                  <a href="{asset_url}" style="display:inline-block; padding:14px 20px; font-size:16px; background-color:#3a5bc7; color:#ffffff; text-decoration:none; border-radius:9999px; font-weight:600; text-transform:uppercase; letter-spacing:0.1em;">
                    Get your gift
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="font-size:14px; color:#555555; padding-top:16px;">
            * Sale and related free asset promotion end October 2, 2025 at 7:59am PT.
          </td>
        </tr>
        
      </table>
    </body>
    </html>
    """

    msg = MIMEText(body, "html")
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
    name, image, desc, url = scrape_asset_info()
    send_email(name, image, desc, url)
