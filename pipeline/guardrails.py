"""Deterministic chat guardrails (specs.md FE13-FE22). All run in code before the LLM, so they cost no LLM call and can be tested."""
import re

MAX_ASKS = 3  # FE14: after three clarifying questions, proceed with defaults
MAX_MSGS_PER_HOUR = 30  # per session; the LLM itself is also capped globally (parser.LLM_CALLS_PER_HOUR)

INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier)?\s*(instructions?|rules?|prompts?)"
    r"|system prompt|developer message|jailbreak|reveal (your )?(instructions|prompt)|you are now\b", re.I)
OUT_OF_SCOPE = re.compile(
    r"(image|video|picture|photo)s?[ -]*(generation|generating|generate|diffusion)|generate\s+(an?\s+)?(image|video)s?|stable diffusion|"
    r"text[- ]to[- ](image|video)|midjourney|mixture[- ]of[- ]experts|\bmoe\b", re.I)
JOB_WORDS = re.compile(
    r"train|fine-?tun|lora|pre-?train|inference|batch|gpu|cpu|model|token|param|server|request|deadline|hours?|job|compute|\d+\s*[bm]\b", re.I)
# A bare greeting or thanks is on-topic: it goes to the agent, which greets back and asks for the job.
GREETING = re.compile(r"^\s*((hi|hello|hey|hiya|howdy|yo|sup)( there)?|good (morning|afternoon|evening)|thanks?( you)?|thx|help|"
                      r"what can you do|who are you|how does this work)\W*$", re.I)
NOT_SURE = re.compile(r"^\s*(not sure|i don'?t know|dunno|no idea|idk|skip)\W*$", re.I)

REFUSALS = {
    "injection": "I can only help describe a compute job. I can't change my instructions or the fixed estimator constants.",
    "scope": "Image or video generation and mixture-of-experts models aren't supported yet. If you know your GPU-hours, say \"I know my GPU-hours\" and give the number, or describe a dense model job (fine-tune, pretrain, inference).",
    "off_topic": "I can help you describe a compute job (training, fine-tuning, inference or batch work) and where you are. What would you like to run?",
}

# Typical defaults (placeholders, labeled "assumed" on screen). job_type has no default: the job can't be guessed.
DEFAULTS = {"n_params": "7B parameters", "tokens": "150 million tokens", "input_tokens": "2000 input tokens", "output_tokens": "500 output tokens",
            "requests": "10000 requests", "server_hours": "40 server-hours", "deadline_utc": "within 2 days"}

SUGGEST = {
    "job_type": ["Fine-tune a model", "LoRA fine-tune a model", "Pretrain a model", "Batch inference", "I know my GPU-hours"],
    "n_params": ["1B", "7B", "13B", "70B", "Not sure"],
    "tokens": ["50 million tokens", "150 million tokens", "1 billion tokens", "Not sure"],
    "input_tokens": ["500 input tokens", "2000 input tokens", "Not sure"],
    "output_tokens": ["200 output tokens", "500 output tokens", "Not sure"],
    "requests": ["10000 requests", "1 million requests", "Not sure"],
    "server_hours": ["10 server-hours", "40 server-hours", "Not sure"],
    "gpu_hours": ["64 GPU-hours", "500 GPU-hours"],
    "deadline_utc": ["within 1 day", "within 2 days", "within a week", "Not sure"],
}
AFTER_ESTIMATE = ["Make it 16 GPUs", "Extend the deadline to a week", "Use A100 GPUs"]


def check(text, has_job):
    """Refusal text if the message must not reach the LLM, else None."""
    if INJECTION.search(text):
        return REFUSALS["injection"]
    if OUT_OF_SCOPE.search(text):
        return REFUSALS["scope"]
    if not has_job and not JOB_WORDS.search(text) and not GREETING.match(text):
        return REFUSALS["off_topic"]
    return None


def apply_defaults(text, needs, asks):
    """-> (new_text, assumed_keys). "Not sure" fills the first missing field (FE15); after MAX_ASKS questions every missing field with a default is filled (FE14)."""
    if not needs:
        return text, []
    if NOT_SURE.match(text) and needs[0] in DEFAULTS:
        return DEFAULTS[needs[0]], [needs[0]]
    if asks >= MAX_ASKS:
        keys = [k for k in needs if k in DEFAULTS]
        if keys:
            return text + ". " + ". ".join(DEFAULTS[k] for k in keys), keys
    return text, []


def assumed_note(keys):
    return "Assumed (typical defaults, not from you): " + ", ".join(DEFAULTS[k] for k in keys) + ". Treat the estimate as rough.\n"


def suggestions(needs, has_estimate):
    if has_estimate:
        return AFTER_ESTIMATE
    return SUGGEST.get(needs[0], []) if needs else []
