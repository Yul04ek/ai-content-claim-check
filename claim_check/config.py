# Model access: environment variables, client and one place for model calls.
# Same pattern as the research agent: Gemini through its OpenAI-compatible endpoint.
#   BASE_URL    https://generativelanguage.googleapis.com/v1beta/openai/
#   API_KEY     the Gemini key (in Colab it is read from the secret GEMINI_API_KEY)
#   MODEL_NAME  for example gemini-3.5-flash-lite

import os
import time

try:
    from dotenv import load_dotenv

    load_dotenv()  # reads a local .env file if there is one (never commit it)
except ImportError:
    pass

try:
    import openai
except ImportError:  # the offline tests run without the package
    openai = None

_RETRY_CODES = (429, 500, 502, 503, 504)


def get_env(key: str) -> str:
    result = os.getenv(key)
    if result is None:
        raise ValueError(f"Environment variable {key} not set")
    return result


def get_client():
    if openai is None:
        raise RuntimeError("The package 'openai' is not installed. Run: pip install -r requirements.txt")
    return openai.OpenAI(base_url=get_env("BASE_URL"), api_key=get_env("API_KEY"))


def chat(client, retries: int = 5, timeout: float = 90, **kwargs):
    """client.chat.completions.create(**kwargs) with a timeout, waiting and retrying.

    Waits and tries again on 429 (rate limit) and 5xx (model overloaded) and on timeouts.
    Stops at once when the DAILY free quota is used up, because waiting does not help.
    """
    fast = client.with_options(timeout=timeout, max_retries=0)  # we do the retrying ourselves
    for attempt in range(retries + 1):
        try:
            return fast.chat.completions.create(**kwargs)
        except (openai.APITimeoutError, openai.APIConnectionError) as error:
            if attempt >= retries:
                raise
            wait = 10 * (attempt + 1)
            print(f"No answer ({type(error).__name__}), waiting {wait} s ...")
            time.sleep(wait)
        except openai.APIStatusError as error:
            if error.status_code == 429 and "PerDay" in str(error.body):
                raise
            if error.status_code in _RETRY_CODES and attempt < retries:
                wait = 20 * (attempt + 1)
                print(f"Model answered {error.status_code}, waiting {wait} s ...")
                time.sleep(wait)
                continue
            raise
