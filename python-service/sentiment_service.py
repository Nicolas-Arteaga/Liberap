import os
import time
import logging
import praw
import requests
from datetime import datetime, timedelta

logger = logging.getLogger("VERGE_SENTIMENT")

class SentimentService:
    """
    Fetches sentiment from Twitter and Reddit.
    Twitter: Hashtags every 5m (Tier Gratuito)
    Reddit: Hot posts every 10m
    """
    def __init__(self):
        self.twitter_bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")
        self.reddit_client_id = os.environ.get("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = "VergeAI/1.0"
        
        self.cache = {"score": 0.5, "last_update": datetime.min}
        self.reddit = None
        if self.reddit_client_id and self.reddit_client_secret:
            try:
                self.reddit = praw.Reddit(
                    client_id=self.reddit_client_id,
                    client_secret=self.reddit_client_secret,
                    user_agent=self.reddit_user_agent
                )
            except Exception as e:
                logger.error(f"Reddit init failed: {e}")

    def get_combined_sentiment(self, symbol="BTC"):
        # Cache TTL: 5 minutes
        if datetime.now() - self.cache["last_update"] < timedelta(minutes=5):
            return self.cache["score"]

        try:
            scores = []
            
            # 1. Reddit Sentiment (r/CryptoCurrency)
            if self.reddit:
                subreddit = self.reddit.subreddit("CryptoCurrency")
                for post in subreddit.hot(limit=10):
                    if symbol.lower() in post.title.lower() or symbol.lower() in post.selftext.lower():
                        # Simple scoring based on title sentiment (could be improved with TextBlob/VADER)
                        scores.append(0.6 if post.score > 100 else 0.5)
            
            # 2. Twitter Sentiment (Mocking for now as Tier Gratuito requires specific setup)
            # In a real scenario, this uses requests.get("https://api.twitter.com/2/tweets/search/recent?query=#BTC")
            if self.twitter_bearer_token:
                logger.info(f"Fetching Twitter sentiment for #{symbol}...")
                scores.append(0.55) # Placeholder
            
            final_score = sum(scores) / len(scores) if scores else 0.5
            self.cache = {"score": final_score, "last_update": datetime.now()}
            return final_score

        except Exception as e:
            logger.error(f"Sentiment fetch failed: {e}. Falling back to neutral.")
            return 0.5

if __name__ == "__main__":
    service = SentimentService()
    print(f"Sentiment Score: {service.get_combined_sentiment('BTC')}")
