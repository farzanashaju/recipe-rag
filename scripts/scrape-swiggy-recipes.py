import json
import asyncio
import re
import hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote
from playwright.async_api import async_playwright

# look for popups or overlays that might block interactions and attempt to close them
async def dismiss_overlay_if_present(page):
    overlay = page.locator('[data-testid="modal-overlay"], [aria-label="Close overlay"]')
    if await overlay.count() > 0:
        try:
            await overlay.first.click(timeout=2000)
            await page.wait_for_timeout(300)
        except Exception:
            # fallback: press escape in case overlay handles keyboard close.
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)

# navigate through alphabetical tabs and collect all recipe links
async def get_all_recipe_links(page):
    print("Connecting to Swiggy Instamart Recipes...")
    await page.goto("https://www.swiggy.com/instamart/recipes", wait_until="networkidle")
    await dismiss_overlay_if_present(page)
    
    # identify alphabet-based tabs
    # divs with class '_30U_M'
    tab_selectors = await page.query_selector_all("div._30U_M > div")
    tab_names = [await t.inner_text() for t in tab_selectors]
    print(f"Found tabs: {tab_names}")

    all_links = set()

    for idx, name in enumerate(tab_names):
        print(f"Processing Tab: {name}...")
        await dismiss_overlay_if_present(page)

        # click the tab by index from the tab row to avoid ambiguous text matches
        tab = page.locator("div._30U_M > div").nth(idx)
        await tab.scroll_into_view_if_needed()
        await tab.click()
        await asyncio.sleep(2) # wait for list to swap

        # scroll within this specific tab
        no_new_count = 0
        tab_links = set()
        
        while no_new_count < 10:
            current_links = await page.eval_on_selector_all(
                'li[data-testid="recipe"] a', 
                "elements => elements.map(e => e.href)"
            )

            # keep only recipe URLs and normalize query strings
            current_links = [
                link.split("?")[0]
                for link in current_links
                if "/instamart/recipe/" in link
            ]
            
            prev_len = len(tab_links)
            tab_links.update(current_links)
            
            if len(tab_links) == prev_len:
                no_new_count += 1
            else:
                no_new_count = 0
            
            # scroll
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(1.5)
        
        print(f"Found {len(tab_links)} recipes in {name}")
        all_links.update(tab_links)

    return sorted(all_links)


# turn raw html into clean strings
def clean_text(value):
    if not value:
        return ""
    return " ".join(value.split())

# "paneer butter masala" to "paneer-butter-masala"
def slugify(value):
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "recipe"


def name_from_url(url):
    path = unquote(urlparse(url).path.rstrip("/"))
    last_part = path.split("/")[-1] if path else "recipe"
    return clean_text(last_part.replace("-", " ")).title() or "Unknown Recipe"

# use regex to pull out specific numbers
# servings, kcal, prep time
def extract_meta_values(meta_text):
    text = clean_text(meta_text)

    servings_match = re.search(r"(Serves?\s*\d+|\d+\s*servings?)", text, flags=re.IGNORECASE)
    time_match = re.search(r"(\d+\s*(?:mins?|minutes?|hrs?|hours?))", text, flags=re.IGNORECASE)
    kcal_match = re.search(r"(\d+\s*kcal)", text, flags=re.IGNORECASE)

    return {
        "servings": servings_match.group(1) if servings_match else "N/A",
        "time": time_match.group(1) if time_match else "N/A",
        "kcal": kcal_match.group(1) if kcal_match else "N/A",
    }


def normalize_stat_value(value, pattern, default="N/A"):
    text = clean_text(value)
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return clean_text(match.group(1)) if match else default


def recipe_output_path(url, recipes_dir):
    slug = slugify(name_from_url(url))
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return recipes_dir / f"{slug}-{digest}.json"


def load_checkpoint(checkpoint_file, total_links):
    if not checkpoint_file.exists():
        return 0

    try:
        with open(checkpoint_file, "r") as f:
            data = json.load(f)
        idx = int(data.get("next_index", 0))
        return max(0, min(idx, total_links))
    except Exception:
        return 0


def save_checkpoint(checkpoint_file, next_index, total_links):
    payload = {
        "next_index": next_index,
        "total_links": total_links,
    }
    with open(checkpoint_file, "w") as f:
        json.dump(payload, f, indent=4)


async def download_recipe_image(page, image_url, recipe_name, image_dir):
    if not image_url:
        return None

    parsed = urlparse(image_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        suffix = ".jpg"

    base_name = slugify(recipe_name)
    digest = hashlib.md5(image_url.encode("utf-8")).hexdigest()[:8]
    file_path = image_dir / f"{base_name}-{digest}{suffix}"

    if file_path.exists():
        return str(file_path)

    try:
        response = await page.request.get(image_url, timeout=60000)
        if not response.ok:
            return None

        image_bytes = await response.body()
        file_path.write_bytes(image_bytes)
        return str(file_path)
    except Exception:
        return None


# extract clean recipe fields and download recipe image
async def scrape_recipe_details(page, url, image_dir):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await dismiss_overlay_if_present(page)
        await page.wait_for_selector('div[data-testid="recipe-page-content-wrapper"]', timeout=20000)
        await page.wait_for_timeout(1000)

        name_locator = page.locator('div[data-testid="IM_SEARCH_PAGE_TITLE"], h1').first
        name = clean_text(await name_locator.inner_text()) if await name_locator.count() > 0 else name_from_url(url)

        meta_text = ""
        meta_locator = page.locator('div[data-testid="recipe-page-info-card-container"]').first
        if await meta_locator.count() > 0:
            meta_text = clean_text(await meta_locator.inner_text())
        meta = extract_meta_values(meta_text)

        # prefer direct stat chips for servings/kcal
        servings_chip = page.locator(
            'div[data-testid="recipe-page-content-wrapper"] span:has-text("Serves")'
        ).first
        if await servings_chip.count() > 0:
            chip_text = clean_text(await servings_chip.text_content() or "")
            meta["servings"] = normalize_stat_value(chip_text, r"(Serves?\s*\d+)", meta["servings"])

        kcal_chip = page.locator(
            'div[data-testid="recipe-page-content-wrapper"] span:has-text("Kcal"), '
            'div[data-testid="recipe-page-content-wrapper"] span:has-text("kcal")'
        ).first
        if await kcal_chip.count() > 0:
            chip_text = clean_text(await kcal_chip.text_content() or "")
            meta["kcal"] = normalize_stat_value(chip_text, r"(\d+\s*kcal)", meta["kcal"])

        image_url = None
        image_locator = page.locator('div[data-testid="recipe-page-content-wrapper"] img').first
        if await image_locator.count() > 0:
            image_url = await image_locator.get_attribute("src")
        image_path = await download_recipe_image(page, image_url, name, image_dir)

        ingredients = []
        ingredients_header = page.get_by_role("heading", name="Ingredients", exact=True)
        if await ingredients_header.count() > 0:
            items = ingredients_header.first.locator("xpath=following-sibling::div[1]//li")
            item_count = await items.count()
            for i in range(item_count):
                value = clean_text(await items.nth(i).inner_text())
                if value and value not in ingredients:
                    ingredients.append(value)

        instructions = []
        instructions_header = page.get_by_role("heading", name="Instructions", exact=True)
        if await instructions_header.count() > 0:
            instructions_container = instructions_header.first.locator("xpath=following-sibling::div[1]").first
            step_items = instructions_container.locator("li, p")
            step_count = await step_items.count()
            for i in range(step_count):
                value = clean_text(await step_items.nth(i).inner_text())
                if len(value) > 8 and value not in instructions:
                    instructions.append(value)

        faqs = []
        faq_questions = page.locator('[data-testid="faq-query"]')
        faq_answers = page.locator('[data-testid="faq-description"]')
        faq_count = max(await faq_questions.count(), await faq_answers.count())
        for i in range(faq_count):
            question = ""
            answer = ""

            if i < await faq_questions.count():
                question = clean_text(await faq_questions.nth(i).inner_text())

            if i < await faq_answers.count():
                answer = clean_text(await faq_answers.nth(i).text_content() or "")

            if question or answer:
                faqs.append({"q": question, "a": answer})

        return {
            "name": name,
            "servings": meta["servings"],
            "time": meta["time"],
            "kcal": meta["kcal"],
            "ingredients": ingredients,
            "instructions": instructions,
            "faqs": faqs,
            "image_url": image_url,
            "image_path": image_path,
            "url": url
        }
    except Exception as e:
        print(f"Error scraping {url}: {type(e).__name__}: {e}")
        return None


async def scrape_recipe_with_retries(page, url, image_dir, retries=3):
    for attempt in range(1, retries + 1):
        data = await scrape_recipe_details(page, url, image_dir)
        if data:
            return data

        if attempt < retries:
            await page.wait_for_timeout(1000 * attempt)

    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        data_dir = Path(__file__).parent.parent / "data"
        image_dir = data_dir / "swiggy_recipe_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        recipes_dir = data_dir / "swiggy_recipe_json"
        recipes_dir.mkdir(parents=True, exist_ok=True)
        links_file = data_dir / "swiggy_recipe_links.json"
        checkpoint_file = data_dir / "swiggy_checkpoint.json"
        failed_file = data_dir / "swiggy_failed_links.json"
        failed_links = []

        if links_file.exists():
            with open(links_file, "r") as f:
                links = json.load(f)
            print(f"Loaded {len(links)} recipe links from {links_file}")
        else:
            links = await get_all_recipe_links(page)
            with open(links_file, "w") as f:
                json.dump(links, f, indent=4)
            print(f"Saved {len(links)} recipe links to {links_file}")

        print(f"Total Unique Recipes Found: {len(links)}")
        start_index = load_checkpoint(checkpoint_file, len(links))
        print(f"Resuming from index {start_index}")

        for i in range(start_index, len(links)):
            link = links[i]
            recipe_file = recipe_output_path(link, recipes_dir)

            if recipe_file.exists():
                save_checkpoint(checkpoint_file, i + 1, len(links))
                if i % 25 == 0:
                    print(f"Progress: {i + 1}/{len(links)} already saved...")
                continue

            data = await scrape_recipe_with_retries(page, link, image_dir, retries=3)
            if data:
                with open(recipe_file, "w") as f:
                    json.dump(data, f, indent=4)
            else:
                print(f"Failed at index {i}: {link}")
                failed_links.append({"index": i, "url": link})

            # always move checkpoint forward so resume continues after cancellation
            save_checkpoint(checkpoint_file, i + 1, len(links))

            if i % 10 == 0:
                print(f"Progress: {i + 1}/{len(links)} processed...")

        save_checkpoint(checkpoint_file, len(links), len(links))
        with open(failed_file, "w") as f:
            json.dump(failed_links, f, indent=4)
        print(f"Failed links saved to {failed_file}")
        print(f"Saved per-recipe JSON files in {recipes_dir}")
        
        await browser.close()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())