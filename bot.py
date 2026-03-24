"""
Crypto Telegram Channel Bot
自动抓取加密货币行情 + 新闻，定时发布到 Telegram 频道

依赖安装：
pip install python-telegram-bot apscheduler requests feedparser python-dotenv aiohttp
"""

import os
import asyncio
import logging
import requests
import feedparser
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

load_dotenv()

# ============================================================
# 配置区 - 修改这里
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "你的Bot Token")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@你的频道用户名")  # 例如 @mycryptochannel

# 发布时间表（24小时制，每天几点发）
SCHEDULE_HOURS = [8, 12, 18, 21]  # 每天4次

# 联盟链接（变现用，可以替换成你自己的推广链接）
AFFILIATE_LINKS = {
    "币安": "https://www.binance.com/referral/earn-together/refer2earn-usdc/claim?hl=zh-TC&ref=GRO_28502_VHX9H&utm_source=default",
    "OKX": "https://www.bvhgkzmywxf.com/join/13124950",
}

# ============================================================
# 日志设置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# 数据获取模块
# ============================================================

def get_crypto_prices() -> dict:
    """从 CoinGecko 免费 API 获取主流币价格（无需 API Key）"""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "bitcoin,ethereum,binancecoin,solana,ripple,cardano,dogecoin",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_market_cap": "true"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"获取价格失败: {e}")
        return {}


def get_fear_greed_index() -> dict:
    """获取加密恐惧贪婪指数"""
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = resp.json()
        return data["data"][0]
    except Exception as e:
        log.error(f"获取恐惧贪婪指数失败: {e}")
        return {"value": "N/A", "value_classification": "未知"}


def get_crypto_news(limit: int = 3) -> list:
    """从 RSS 聚合加密新闻"""
    feeds = [
        "https://cointelegraph.com/rss",
        "https://coindesk.com/arc/outboundfeeds/rss/",
    ]
    articles = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:2]:
                articles.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "source": feed.feed.get("title", ""),
                })
        except Exception as e:
            log.error(f"解析RSS失败 {feed_url}: {e}")
    return articles[:limit]


# ============================================================
# 消息格式化模块
# ============================================================

COIN_EMOJI = {
    "bitcoin": "₿",
    "ethereum": "Ξ",
    "binancecoin": "🔶",
    "solana": "◎",
    "ripple": "✕",
    "cardano": "🔵",
    "dogecoin": "🐕",
}

COIN_NAME = {
    "bitcoin": "Bitcoin",
    "ethereum": "Ethereum",
    "binancecoin": "BNB",
    "solana": "Solana",
    "ripple": "XRP",
    "cardano": "Cardano",
    "dogecoin": "Dogecoin",
}

def format_change(change: float) -> str:
    if change is None:
        return "N/A"
    arrow = "▲" if change >= 0 else "▼"
    return f"{arrow} {abs(change):.2f}%"

def format_price_message(prices: dict, fg: dict) -> str:
    """格式化行情消息"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fg_value = fg.get("value", "?")
    fg_class = fg.get("value_classification", "?")

    lines = [
        f"📊 *加密市场行情播报*",
        f"🕐 {now} (UTC+8)",
        f"",
        f"💹 *主流币实时价格*",
        f"{'─' * 28}",
    ]

    for coin_id, data in prices.items():
        emoji = COIN_EMOJI.get(coin_id, "🪙")
        name = COIN_NAME.get(coin_id, coin_id.upper())
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        change_str = format_change(change)
        price_str = f"${price:,.2f}" if price > 1 else f"${price:.4f}"
        lines.append(f"{emoji} *{name}*: `{price_str}` {change_str}")

    lines += [
        f"",
        f"😨 *市场情绪*: {fg_value}/100 — {fg_class}",
        f"",
        f"💡 *风险提示*: 加密市场波动剧烈，以上信息仅供参考，不构成投资建议。",
        f"",
        f"🏦 交易所推荐: [币安](https://binance.com) | [OKX](https://okx.com)",
        f"",
        f"👉 关注本频道获取每日实时行情",
    ]
    return "\n".join(lines)


def format_news_message(articles: list) -> str:
    """格式化新闻消息"""
    if not articles:
        return ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📰 *加密市场早报*",
        f"🕐 {now} (UTC+8)",
        f"{'─' * 28}",
    ]
    for i, article in enumerate(articles, 1):
        lines.append(f"{i}\\. [{article['title']}]({article['link']})")
        lines.append(f"   📌 来源: {article['source']}")
        lines.append("")

    lines += [
        f"🔔 每日追踪市场动态，欢迎转发！",
        f"",
        f"📊 行情 | 📰 新闻 | 💹 分析",
    ]
    return "\n".join(lines)


# ============================================================
# 发布模块
# ============================================================

async def post_market_update(bot: Bot):
    """发布行情更新"""
    log.info("开始发布行情更新...")
    prices = get_crypto_prices()
    fg = get_fear_greed_index()

    if not prices:
        log.warning("价格数据为空，跳过发布")
        return

    msg = format_price_message(prices, fg)
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        log.info("✅ 行情发布成功")
    except Exception as e:
        log.error(f"发布行情失败: {e}")


async def post_news_update(bot: Bot):
    """发布新闻更新"""
    log.info("开始发布新闻...")
    articles = get_crypto_news(limit=3)

    if not articles:
        log.warning("新闻为空，跳过发布")
        return

    msg = format_news_message(articles)
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )
        log.info("✅ 新闻发布成功")
    except Exception as e:
        log.error(f"发布新闻失败: {e}")


# ============================================================
# 统计模块（记录发布历史）
# ============================================================

import json

STATS_FILE = "stats.json"

def load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"total_posts": 0, "last_post": None, "errors": 0}

def save_stats(stats: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def record_post(success: bool = True):
    stats = load_stats()
    if success:
        stats["total_posts"] += 1
        stats["last_post"] = datetime.now().isoformat()
    else:
        stats["errors"] += 1
    save_stats(stats)


# ============================================================
# 主程序 & 调度器
# ============================================================

async def scheduled_job(bot: Bot):
    """定时任务主函数"""
    hour = datetime.now().hour
    log.info(f"执行定时任务，当前时间: {hour}:00")

    # 早上8点发新闻 + 行情
    if hour == 8:
        await post_news_update(bot)
        await asyncio.sleep(5)
        await post_market_update(bot)
    else:
        # 其他时间只发行情
        await post_market_update(bot)

    record_post(success=True)


async def main():
    log.info("🚀 Bot 启动中...")
    bot = Bot(token=BOT_TOKEN)

    # 验证 Bot
    me = await bot.get_me()
    log.info(f"✅ Bot 已连接: @{me.username}")

    # 设置调度器
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            scheduled_job,
            "cron",
            hour=hour,
            minute=0,
            args=[bot]
        )
        log.info(f"📅 已设置定时任务: 每天 {hour:02d}:00")

    scheduler.start()
    log.info("⏰ 调度器已启动，等待执行...")

    # 立即发一次测试（可注释掉）
    log.info("发送启动测试消息...")
    await post_market_update(bot)

    # 保持运行
    try:
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        log.info("Bot 已停止")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
