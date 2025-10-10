import os
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone
from emailoctopus_sdk import Client


# EmailOctopus Configuration - Get from GitHub Secrets
API_KEY = os.getenv("API_KEY")
LIST_ID = os.getenv("LIST_ID")

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

def scrape_asset_info() -> tuple[str, str, str, str]:
	"""Scrapes the Unity Asset Store for the free asset of the week using new selectors."""
	try:
		url = "https://assetstore.unity.com/publisher-sale"
		response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
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
	
	try:
		update_all_contacts_fields(asset, image, description, url)
		sys.exit(0)
	except Exception as e:
		log.error(f"Unexpected error while updating fields: {e}")
		sys.exit(1)

if __name__ == "__main__":
	main()

# Exit code defintions:
# 0 = success
# 1 = generic error
# 2 = missing config
# 3 = data issue (e.g. asset not found)
