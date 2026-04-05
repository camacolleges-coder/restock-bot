import asyncio
import aiohttp
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

PRODUCTS = [
    {
        "name": "Pokemon Prismatic Evolutions Booster Bundle",
        "retailer": "Amazon",
        "asin": "B0DJLXB7G8",
        "url": "https://www.amazon.com/dp/B0DJLXB7G8",
        "image_url": "",
    },
    {
        "name": "Pokemon Scarlet Violet Booster Pack",
        "retailer": "Target",
        "tcin": "89865319",
        "url": "https://www.target.com/p/-/A-89865319",
        "image_url": "",
    },
    {
        "name": "Pokemon Elite Trainer Box",
        "retailer": "Walmart",
        "item_id": "5678901234",
        "url": "https://www.walmart.com/ip/5678901234",
        "image_url": "",
    },
    {
        "name": "Pokemon 151 Ultra Premium Collection",
        "retailer": "PokemonCenter",
        "url": "https://www.pokemoncenter.com/product/290-80738",
        "image_url": "",
    },
]

previous_status = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

RETAILER_COLORS = {
    "Amazon": 0xFF9900,
    "Target": 0xCC0000,
    "Walmart": 0x007DC6,
    "PokemonCenter": 0xFFCB05,
}

# ══ DISCORD ══
async def send_discord_alert(session, product, price=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = RETAILER_COLORS.get(product["retailer"], 0x57F287)
    fields = [
        {"name": "🏪 Retailer", "value": product["retailer"], "inline": True},
        {"name": "📊 Status", "value": "🟢 **IN STOCK**", "inline": True},
    ]
    if price:
        fields.append({"name": "💰 Price", "value": price, "inline": True})

    embed = {
        "title": f"🔔 {product['name']}",
        "url": product["url"],
        "color": color,
        "fields": fields,
        "footer": {"text": f"RestockBot • {now}"},
    }
    if product.get("image_url"):
        embed["thumbnail"] = {"url": product["image_url"]}

    payload = {
        "username": "RestockBot",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "content": "@everyone 🚨 Restock detected — grab it before it's gone!",
        "embeds": [embed],
    }
    try:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
            if resp.status in (200, 204):
                logger.info(f"✅ Discord alert: {product['name'][:40]}")
            else:
                logger.error(f"❌ Discord {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.error(f"❌ Discord error: {e}")

async def send_discord_startup(session):
    payload = {
        "username": "RestockBot",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [{
            "title": "🤖 Restock Monitor — Online",
            "color": 0x57F287,
            "fields": [
                {"name": "📦 Products tracked", "value": str(len(PRODUCTS)), "inline": True},
                {"name": "⏱ Check interval", "value": f"every {CHECK_INTERVAL}s","inline": True},
                {"name": "🏪 Retailers", "value": "Amazon · Target · Walmart · Pokemon Center", "inline": False},
            ],
            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        }]
    }
    try:
        async with session.post(DISCORD_WEBHOOK_URL, json=payload) as resp:
            if resp.status in (200, 204):
                logger.info("✅ Startup message sent to Discord")
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")

# ══ SCRAPERS ══
async def check_amazon(session, product):
    asin = product.get("asin")
    url = f"https://www.amazon.com/gp/product/ajax/ref=dp_aod_unknown_mbc?asin={asin}&pc=dp&experienceId=aodAjaxMain"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                text = await r.text()
                return ("In Stock" in text or "Add to Cart" in text), ""
    except Exception as e:
        logger.warning(f"Amazon ({asin}): {e}")
    return False, ""

async def check_target(session, product):
    tcin = product.get("tcin")
    url = f"https://redsky.target.com/redsky_aggregations/v1/web/pdp_client_v1?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&tcin={tcin}&store_id=3991&zip=10001&state=NY&latitude=40.71&longitude=-74.00&pricing_store_id=3991"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                avail = data.get("data",{}).get("product",{}).get("fulfillment",{}).get("shipping_options",{}).get("availability_status","")
                price = data.get("data",{}).get("product",{}).get("price",{}).get("current_retail",0)
                return avail in ("IN_STOCK","LIMITED_STOCK"), (f"${price:.2f}" if price else "")
    except Exception as e:
        logger.warning(f"Target ({tcin}): {e}")
    return False, ""

async def check_walmart(session, product):
    item_id = product.get("item_id")
    url = f"https://www.walmart.com/terra-firma/item/{item_id}?rgs=DESKTOP"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                avail = data.get("availabilityStatus","")
                price = data.get("priceMap",{}).get("price","")
                return avail == "IN_STOCK", (f"${price}" if price else "")
    except Exception as e:
        logger.warning(f"Walmart ({item_id}): {e}")
    return False, ""

async def check_pokemon_center(session, product):
    try:
        async with session.get(product["url"], headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                text = await r.text()
                return ('"availability":"InStock"' in text or "Add to Cart" in text), ""
    except Exception as e:
        logger.warning(f"PokemonCenter: {e}")
    return False, ""

CHECKER_MAP = {
    "Amazon": check_amazon,
    "Target": check_target,
    "Walmart": check_walmart,
    "PokemonCenter": check_pokemon_center,
}

# ══ MAIN LOOP ══
async def check_product(session, product):
    checker = CHECKER_MAP.get(product["retailer"])
    if not checker:
        return
    in_stock, price = await checker(session, product)
    key = f"{product['retailer']}_{product.get('asin') or product.get('tcin') or product.get('item_id') or product['name']}"
    prev = previous_status.get(key)

    if prev is None:
        logger.info(f"{'🟢' if in_stock else '🔴'} [{product['retailer']}] {product['name'][:40]}")
        previous_status[key] = in_stock
        return

    if in_stock != prev:
        previous_status[key] = in_stock
        logger.info(f"🔔 CHANGE [{product['retailer']}] {product['name'][:40]} → {'IN STOCK' if in_stock else 'OUT'}")
        if in_stock:
            await send_discord_alert(session, product, price)

async def main():
    logger.info(f"🚀 Starting — {len(PRODUCTS)} products, every {CHECK_INTERVAL}s")
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        await send_discord_startup(session)
        while True:
            await asyncio.gather(*[check_product(session, p) for p in PRODUCTS], return_exceptions=True)
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
