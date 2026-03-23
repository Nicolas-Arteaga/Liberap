import os
import time
import logging
import json
import redis
from datetime import datetime

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
        
        # Redis Connection
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))
        self.r = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        
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
        cache_key = f"sentiment:{symbol.upper()}"
        
        # Check Redis Cache First
        cached_score = self.r.get(cache_key)
        if cached_score:
            return float(cached_score)

        try:
            scores = []
            
            # 1. Reddit Sentiment
            if self.reddit:
                subreddit = self.reddit.subreddit("CryptoCurrency")
                for post in subreddit.hot(limit=10):
                    if symbol.lower() in post.title.lower() or symbol.lower() in post.selftext.lower():
                        scores.append(0.6 if post.score > 100 else 0.5)
            
            # 2. Twitter Sentiment (Placeholder)
            if self.twitter_bearer_token:
                scores.append(0.55)
            
            final_score = sum(scores) / len(scores) if scores else 0.5
            
            # Set Redis Cache with 5 min TTL
            self.r.setex(cache_key, 300, str(final_score))
            
            return final_score

        except Exception as e:
            logger.error(f"Sentiment fetch failed: {e}. Falling back to neutral.")
            return 0.5

if __name__ == "__main__":
    service = SentimentService()
    print(f"Sentiment Score: {service.get_combined_sentiment('BTC')}")
