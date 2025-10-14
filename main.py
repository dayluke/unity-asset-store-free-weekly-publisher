import os
import sys
import json
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone
from emailoctopus_sdk import Client


# EmailOctopus Configuration - Get from GitHub Secrets
API_KEY = os.getenv("API_KEY")
LIST_ID = os.getenv("LIST_ID")

# Unity Asset Store Configuration and Selectors
ASSET_STORE_URL = "https://assetstore.unity.com"
ASSET_PARENT_SELECTOR = "[data-type='CalloutSlim']"
ASSET_NAME_SELECTOR = "h2"
ASSET_IMAGE_SELECTOR = "img"
ASSET_BUTTON_SELECTOR = "a"
ASSET_DESCRIPTION_SELECTOR = "body"
ASSET_PRICE_SELECTOR = "._3Yjml"

# Savings File Configuration
SAVINGS_FILE = "savings.json"


logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# region: Unity Asset Store


def scrape_asset_info() -> tuple[str, str, str, str]:
	"""Scrapes the Unity Asset Store for the free asset of the week using new selectors."""
	try:
		url = f"{ASSET_STORE_URL}/publisher-sale"
		response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
		response.raise_for_status()
		soup = BeautifulSoup(response.content, "html.parser")

		free_asset_section = soup.select_one(ASSET_PARENT_SELECTOR)

		if free_asset_section:
			asset_name_element = free_asset_section.find(ASSET_NAME_SELECTOR)
			asset_name = asset_name_element.get_text(strip=True) if asset_name_element else "Asset Name Not Found"

			asset_image_element = free_asset_section.find(ASSET_IMAGE_SELECTOR)
			asset_image = asset_image_element.get("src") if asset_image_element else ""

			asset_button_element = free_asset_section.find(ASSET_BUTTON_SELECTOR)
			asset_url = asset_button_element.get("href") if asset_button_element else ""

			asset_description_element = free_asset_section.find(class_=ASSET_DESCRIPTION_SELECTOR)
			asset_description = asset_description_element.get_text(strip=True) if asset_description_element else "Asset Description Not Found"
			
			return asset_name, asset_image, asset_description, asset_url
		else:
			log.warning("Could not find the free asset section using the specified selector.")
			return None, None, None, None
			
	except requests.exceptions.RequestException as e:
		log.error(f"Error fetching the URL: {e}")
		return None, None, None, None


def next_weekday_at_time(weekday: int, target_time: time, tz=timezone.utc) -> datetime:
	now = datetime.now(tz)
	days_ahead = (weekday - now.weekday() + 7) % 7
	if days_ahead == 0 and now.time() >= target_time:
		days_ahead = 7

	next_day = (now + timedelta(days=days_ahead)).date()
	return datetime.combine(next_day, target_time, tzinfo=tz)


def get_expiry_date() -> str:
	# Get next Thursday at 15:00 UTC
	next_thursday_3pm_utc = next_weekday_at_time(weekday=3, target_time=time(15, 0))
	# Format it like: October 2, 2025 at 3:00PM UTC
	return next_thursday_3pm_utc.strftime("%B %-d, %Y at %-I:%M%p UTC")


# endregion: Unity Asset Store

# region: Email Octopus


def update_all_contacts_fields(asset: str, image: str, description: str, url: str):
	"""Updates all subscribers' asset-related fields, triggering the automation to send the email."""
	client = Client(api_key=API_KEY)
	contacts = client.get_all_contacts(list_id=LIST_ID)
	fields = {
		"AssetName": asset,
		"AssetImage": image,
		"AssetDescription": description,
		"AssetURL": url,
		"AssetExpiry": get_expiry_date()
	}

	success_count = 0
	failed_count = 0
	for batch in client.update_contacts_in_batches(list_id=LIST_ID, contacts=contacts, fields=fields):
		success_count += len(batch['success'])
		failed_count += len(batch['errors'])
	
	log.info(f"Success: {success_count}, Failed: {failed_count}")


# endregion: Email Octopus

# region: Price Scraping


def scrape_asset_price(asset_url: str) -> float:
	"""Visits the asset's page and scrapes its regular price."""
	if not asset_url.startswith("https://"):
		asset_url = ASSET_STORE_URL + asset_url

	try:
		log.info(f"Scraping price from: {asset_url}")
		response = requests.get(asset_url, headers={'User-Agent': 'Mozilla/5.0'})
		response.raise_for_status()
		soup = BeautifulSoup(response.content, "html.parser")
		
		price_element = soup.select_one(ASSET_PRICE_SELECTOR)

		if price_element:
			price_text = price_element.contents[-1].get_text(strip=True)
			log.info(f"Found price: {price_text}")
			number = float(price_text.replace("€", ""))
			return number
		else:
			log.warning("Could not find the price element on the page.")
			return 0.0
	except requests.exceptions.RequestException as e:
		log.error(f"Error fetching the asset price URL: {e}")
		return 0.0


def read_total_savings() -> float:
	"""Reads the total savings from the JSON file."""
	try:
		with open(SAVINGS_FILE, 'r') as f:
			data = json.load(f)
			return float(data.get("total_savings", 0.0))
	except FileNotFoundError:
		log.warning(f"'{SAVINGS_FILE}' not found. Starting savings from 0.")
		return 0.0
	except (json.JSONDecodeError, TypeError):
		log.error(f"Could not read or parse '{SAVINGS_FILE}'. Treating savings as 0.")
		return 0.0


def save_total_savings(new_total: float):
	"""Saves the new total savings to the JSON file."""
	data = {"total_savings": round(new_total, 2)}
	with open(SAVINGS_FILE, 'w') as f:
		json.dump(data, f, indent=2)
	log.info(f"Successfully saved new total savings: {data['total_savings']:.2f}")


# endregion: Price Scraping

# region: Main


def main():
	log.info("Starting the Unity Asset Notifier script...")
	
	missing_vars = []
	if not API_KEY:
		missing_vars.append("API_KEY")
	if not LIST_ID:
		missing_vars.append("LIST_ID")
	
	if missing_vars:
		log.error(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
		sys.exit(2)
	
	asset, image, description, url = scrape_asset_info()
	if not all ([asset, description, image, url]):
		log.warning("Could not find asset information. No fields will be updated.")
		sys.exit(3)
	
	log.info(f"Found asset: {asset}")

	asset_price = scrape_asset_price(url)
	if asset_price > 0.0:
		current_savings = read_total_savings()
		new_savings = current_savings + asset_price
		save_total_savings(new_savings)
	else:
		log.warning("Asset price is 0 or could not be found. Savings will not be updated.")
	
	try:
		update_all_contacts_fields(asset, image, description, url)
		sys.exit(0)
	except Exception as e:
		log.error(f"Unexpected error while updating fields: {e}")
		sys.exit(1)


if __name__ == "__main__":
	main()


# endregion: Main

# Exit code defintions:
# 0 = success
# 1 = generic error
# 2 = missing config
# 3 = data issue (e.g. asset not found)
