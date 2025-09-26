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
        <head>
        <style>
          body {{
            padding: 1rem;
          }}
        
          .expanding-container {{
            position: relative;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            padding: 4rem;
            background: url('{asset_image}') no-repeat center center/cover;
            color: white;
            border-radius: .75rem;
            overflow: hidden;
          }}
        
          .vignette-overlay {{
            position: absolute;
            inset: 0;
            background: linear-gradient(to bottom, rgba(0,0,0,0) 20%, rgba(0,0,0,1) 100%);
            z-index: 0;
            pointer-events: none;
          }}
        
          .content {{
            position: relative;
            z-index: 1;
            width: 60%;
            padding-left: 2rem;
          }}
        
          .title {{
            font-family: Helvetica, sans-serif;
            font-size: .875rem;
            line-height: 1.25rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: .18em;
            margin-bottom: 1.25rem;
          }}
        
          .subtitle {{
            font-family: Helvetica, sans-serif;
            font-size: 2.125rem;
            line-height: 2.375rem;
            font-weight: 700;
            letter-spacing: -.006em;
          }}
        
          .description {{
            font-family: Helvetica, sans-serif;
            margin-top: 1.25rem;
            font-size: 1.125rem;
            line-height: 1.5rem;
            letter-spacing: -.006em;
          }}
        
          .button-container {{
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            margin-left: auto;
            padding-left: 1rem;
          }}
        
          .button-container a {{
            text-decoration: none;
            padding: 0.9rem 1rem;
            font-family: Helvetica, sans-serif;
            font-size: 1rem;
            border: none;
            border-radius: 9999px;
            background-color: rgb(58 91 199);
            color: white;
            cursor: pointer;
            transition: background-color 0.3s ease;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: .1em;
          }}
        
          .button-container a:hover {{
            background-color: rgb(66 104 230);
          }}
        
          .lower-text {{
            font-family: Helvetica, sans-serif;
            font-size: .875rem;
            line-height: 1.25rem;
            margin: 0.75rem 0 0 0;
          }}
        
          /* Responsive stacking on smaller screens */
          @media (max-width: 710px) {{
            .expanding-container {{
              flex-direction: column;
              align-items: flex-start;
            }}
        
            .content {{
              margin: 0 auto;
              text-align: center;
            }}
        
            .button-container {{
              margin: 1rem auto;
            }}
          }}
        </style>
        </head>
        <body>
            <div class="expanding-container">
                <div class="vignette-overlay"></div>
                
                <div class="content">
                    <h2 class="title">Free asset of the week</h2>
                    <h1 class="subtitle">{asset_name}</h1>
                    <p class="description">{asset_description}</p>
                </div>
                
                <div class="button-container">
                    <a href={asset_url}>Get your gift</a>
                </div>
            </div>
            <p class="lower-text">* Sale and related free asset promotion end {expiry_date_formatted}.</p>
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
